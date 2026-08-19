"""谈判引擎节点：意图解析 → 战术选择 → 话术生成 → 底线检查（+兜底）。

每个节点保持纯状态函数，流式桥接由路由层处理（PRD 9.4）。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable

from app.engine.extractor import first_price
from app.engine.llm import BaseLLM, rule_intent
from app.engine.state import NegotiationState
from app.engine.tactics import (
    DEFAULT_TACTIC,
    TACTIC_PROMPTS,
    TacticContext,
    TacticDecision,
    select_tactic,
    update_tactic_context,
)

logger = logging.getLogger(__name__)

MAX_RETRY = 3  # 底线检查最多重试 3 次（PRD 功能 1）

DIM_VALUE_RE = re.compile(r"[^0-9]{0,8}(\d+(?:\.\d+)?)\s*(万元|万|元|个月|天|年|%|％)?")
DIM_VALUE_REVERSE_RE = re.compile(r"(\d+(?:\.\d+)?)[^0-9]{0,4}")

INTENT_PROMPT = """[意图提取]
你是谈判对话分析器。从用户发言中提取结构化信息，只输出 JSON：
{{
  "intent_type": "offer|reject|ask|concede|other",
  "price": 数字或 null（用户报出的价格，单位万元，无则 null）,
  "concessions": ["用户做出的让步描述"],
  "emotion": "eager|angry|neutral|calm",
  "aggression_level": "high|low"
}}
用户发言: {user_msg}"""

TACTIC_FALLBACK_PROMPT = """[战术兜底]
当前规则引擎未命中任何战术。请从以下战术中选择最合适的一个并输出 JSON：
{{
  "tactic": "good_cop_bad_cop|time_pressure|last_ultimatum|false_bottom|divide_conquer|silence_pressure|concession_bait|info_asymmetry",
  "reason": "选择理由"
}}
场景: {scenario_title}
当前阶段: {phase}
用户意图: {intent}
最近用户发言: {user_msg}"""

UTTERANCE_PROMPT = """[话术生成]
{role}

{tactic_hint}

[历史对话]
{history}
{rag_section}
[用户发言] 对方说: {user_msg}
{retry_hint}
[指令] 以角色身份回应，保持战术一致性。回复中必须给出明确数值（如价格/天数/年限），格式如「报价：XX 万」「付款周期：XX 天」。{dim_hints}
请直接输出回复内容，不要解释。"""


# ---------------------------------------------------------------------------
# 状态辅助
# ---------------------------------------------------------------------------


def derive_phase(state: NegotiationState) -> str:
    round_no = state.get("round", 1)
    if round_no <= 1:
        return "opening"
    if state.get("rounds_since_last_progress", 0) > 3:
        return "deadlock"
    return "core"


def derive_firmness(state: NegotiationState) -> str:
    intent = state.get("intent") or {}
    if intent.get("concessions"):
        return "low"
    if intent.get("intent_type") in ("reject", "offer"):
        return "high"
    return "low"


# ---------------------------------------------------------------------------
# 节点
# ---------------------------------------------------------------------------


async def intent_node(state: NegotiationState, llm: BaseLLM) -> dict:
    user_msg = state.get("user_message", "")
    try:
        intent = await llm.ainvoke_json(
            INTENT_PROMPT.format(user_msg=user_msg), light=True
        )
        intent = {k: intent.get(k) for k in ("intent_type", "price", "concessions", "emotion", "aggression_level")}
    except (ValueError, TypeError) as exc:
        logger.warning("意图解析 LLM 失败，使用规则兜底: %s", exc)
        intent = rule_intent(user_msg)
    return {"intent": intent}


async def tactic_node(state: NegotiationState, llm: BaseLLM) -> dict:
    scenario = state.get("scenario") or {}
    intent = state.get("intent") or {}
    ctx = TacticContext(
        phase=derive_phase(state),
        round=state.get("round", 1),
        scenario=scenario,
        user_intent=intent,
        user_concede_count=state.get("user_concede_count", 0),
        user_firmness=derive_firmness(state),
        last_user_msg_length=len(state.get("user_message", "")),
        rounds_since_last_progress=state.get("rounds_since_last_progress", 0),
        used_tactics=state.get("used_tactics") or [],
        tactic_context=state.get("tactic_context") or {},
    )
    decision: TacticDecision = select_tactic(ctx)
    if decision.name == DEFAULT_TACTIC and llm.configured:
        try:
            fallback = await llm.ainvoke_json(
                TACTIC_FALLBACK_PROMPT.format(
                    scenario_title=scenario.get("title", ""),
                    phase=ctx.phase,
                    intent=intent.get("intent_type"),
                    user_msg=state.get("user_message", ""),
                ),
                light=True,
            )
            if fallback.get("tactic"):
                decision = TacticDecision(name=fallback["tactic"], reason=fallback.get("reason", "LLM 兜底"))
        except (ValueError, TypeError) as exc:
            logger.warning("战术 LLM 兜底失败，保留规则结果: %s", exc)
    return {
        "selected_tactic": decision.name,
        "tactic_reason": decision.reason,
        "tactic_sub_role": decision.sub_role,
        "tactic_context": update_tactic_context(state.get("tactic_context") or {}, decision),
    }


def _history_text(state: NegotiationState) -> str:
    lines = []
    for msg in state.get("history") or []:
        who = "你" if msg["role"] == "assistant" else "对方"
        lines.append(f"{who}: {msg['content']}")
    return "\n".join(lines[-8:]) or "（无）"


def _dim_hints(scenario: dict) -> str:
    hints = []
    for dim in scenario.get("dimensions", []):
        hint = dim.get("prompt_hint")
        if hint:
            hints.append(hint)
    return " ".join(hints)


async def utterance_node(state: NegotiationState, llm: BaseLLM, rag=None, stream=None) -> dict:
    scenario = state.get("scenario") or {}
    tactic = state.get("selected_tactic") or DEFAULT_TACTIC
    tactic_prompt = TACTIC_PROMPTS.get(tactic, TACTIC_PROMPTS[DEFAULT_TACTIC])
    sub_role = state.get("tactic_sub_role")
    if sub_role:
        tactic_prompt = tactic_prompt.format(sub_role=sub_role)
    retry_hint = ""
    if state.get("retry_reason"):
        retry_hint = (
            f"[上轮被驳回] 驳回原因: {state['retry_reason']}。"
            "请重新生成不突破底线的回复，务必把数值改到安全范围内。"
        )
    rag_section = ""
    if rag is not None:
        try:
            # role='assistant'：只取对手应答作参考，用户消息不得注入 prompt（防 LLM 回显）
            refs = rag.search(
                state.get("scenario_id", ""),
                state.get("user_message", ""),
                top_k=3,
                role="assistant",
            )
            refs = [r for r in refs if r.get("role") == "assistant"]
            if refs:
                lines = "\n".join(f"  - {r['text']}" for r in refs if r.get("text"))
                rag_section = f"[历史参考] 相似情境之前这样应答过:\n{lines}\n"
        except Exception as exc:  # noqa: BLE001 RAG 故障不阻断话术生成
            logger.warning("RAG 检索失败，跳过历史参考: %s", exc)
    prompt = UTTERANCE_PROMPT.format(
        role=scenario.get("opponent_role", ""),
        tactic_hint=f"[战术] 当前使用: {tactic}。{tactic_prompt}",
        history=_history_text(state),
        rag_section=rag_section,
        user_msg=state.get("user_message", ""),
        retry_hint=retry_hint,
        dim_hints=_dim_hints(scenario),
    )
    # 伪流式：完整生成 → 底线检查 → 展示端分片（negotiation._stream_text）。
    # stream 非空时走真流式（保留能力）；重试轮恒走非流式（避免残影/重复拼接）。
    if stream is not None and not state.get("retry_count"):
        parts: list[str] = []
        async for piece in llm.astream(prompt):
            parts.append(piece)
            try:
                await stream(piece)
            except Exception as exc:  # noqa: BLE001 转发失败不阻断生成
                logger.warning("流式转发失败: %s", exc)
        reply = "".join(parts)
    else:
        reply = await llm.ainvoke(prompt)
    return {"reply": reply.strip()}


def extract_dim_value(reply: str, dim: dict) -> float | None:
    """从回复中提取某维度数值；带单位关键字优先，价格类兜底 first_price。"""
    for kw in dim.get("keywords", []):
        pos = reply.find(kw)
        if pos == -1:
            continue
        m = DIM_VALUE_RE.search(reply, pos, pos + 12)
        if m:
            return float(m.group(1))
        m_rev = DIM_VALUE_REVERSE_RE.search(reply[max(0, pos - 12) : pos + 1])
        if m_rev:
            return float(m_rev.group(1))
    if dim.get("unit") == "wan":
        return first_price(reply)
    return None


def check_bottom_lines(reply: str, scenario: dict) -> list[str]:
    """纯规则底线检查（PRD 9.3/功能 1）：返回违规描述列表，空 = 通过。"""
    violations = []
    for dim in scenario.get("dimensions", []):
        if not any(kw in reply for kw in dim.get("keywords", [])):
            continue
        val = extract_dim_value(reply, dim)
        if val is None:
            continue
        bottom = dim["bottom_line"]
        if dim["direction"] == "min" and val < bottom:
            violations.append(f"{dim['label']} {val} 低于底线 {bottom}")
        elif dim["direction"] == "max" and val > bottom:
            violations.append(f"{dim['label']} {val} 超过上限 {bottom}")
    return violations


def bottom_line_node(state: NegotiationState) -> dict:
    reply = state.get("reply") or ""
    scenario = state.get("scenario") or {}
    violations = check_bottom_lines(reply, scenario)
    if violations:
        retry_count = state.get("retry_count", 0) + 1
        if retry_count > MAX_RETRY:
            return {
                "reply_blocked": True,
                "retry_count": retry_count,
                "bottom_line_status": "fallback",
            }
        return {
            "reply_blocked": True,
            "retry_count": retry_count,
            "retry_reason": "；".join(violations),
            "bottom_line_status": "blocked",
        }
    return {
        "reply_blocked": False,
        "retry_reason": None,
        "bottom_line_status": "ok",
        "opponent_offer": {"reply": reply, "numbers": first_price(reply)},
    }


def fallback_node(state: NegotiationState) -> dict:
    scenario = state.get("scenario") or {}
    templates = scenario.get("safe_fallback") or []
    tactic = state.get("selected_tactic") or DEFAULT_TACTIC
    if not templates:
        from app.engine.tactics import SAFE_TEMPLATES

        templates = SAFE_TEMPLATES.get(tactic, SAFE_TEMPLATES[DEFAULT_TACTIC])
    idx = (state.get("round", 1) - 1) % len(templates)
    return {
        "reply": templates[idx],
        "reply_blocked": False,
        "retry_reason": None,
        "bottom_line_status": "fallback",
        "opponent_offer": None,
    }


# ---------------------------------------------------------------------------
# 图构建
# ---------------------------------------------------------------------------

Node = Callable[[NegotiationState, BaseLLM], Awaitable[dict]] | Callable[[NegotiationState], dict]


def build_graph(llm: BaseLLM, checkpointer=None, rag=None, stream=None):
    from langgraph.graph import END, START, StateGraph

    async def _intent(state): return await intent_node(state, llm)
    async def _tactic(state): return await tactic_node(state, llm)
    async def _utterance(state): return await utterance_node(state, llm, rag=rag, stream=stream)

    def _route(state: NegotiationState) -> str:
        if state.get("reply_blocked"):
            return "fallback" if state.get("bottom_line_status") == "fallback" else "blocked"
        return "ok"

    g = StateGraph(NegotiationState)
    g.add_node("intent", _intent)
    g.add_node("tactic", _tactic)
    g.add_node("utterance", _utterance)
    g.add_node("bottom_line", bottom_line_node)
    g.add_node("fallback", fallback_node)
    g.add_edge(START, "intent")
    g.add_edge("intent", "tactic")
    g.add_edge("tactic", "utterance")
    g.add_edge("utterance", "bottom_line")
    g.add_conditional_edges(
        "bottom_line", _route, {"ok": END, "blocked": "utterance", "fallback": "fallback"}
    )
    g.add_edge("fallback", END)
    return g.compile(checkpointer=checkpointer)
