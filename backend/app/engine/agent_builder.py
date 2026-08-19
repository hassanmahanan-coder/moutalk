"""ReAct Agent 谈判引擎（langchain.agents.create_agent，langgraph 1.x）。

Source: https://reference.langchain.com/python/langchain/agents/factory/create_agent
create_agent(model, tools, *, system_prompt, checkpointer) -> CompiledStateGraph
输入 {"messages": [...]}，最终 AIMessage.content 为回复。

设计（保留确定性护栏）：
- 意图规则解析 / 战术规则库 / 记忆检索 / 底线校验 注册为 Tools，供 LLM 自主调用；
- 底线校验做双层：prompt 强制调用 validate_reply + 引擎外层规则硬校验（违规走 fallback 模板）；
- 双模式：有 key（configured=True）走 Agent；无 key 走原 5 节点工作流（Mock 无法模拟 tool calling）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import tool

from app.engine.extractor import first_price
from app.engine.llm import BaseLLM, rule_intent
from app.engine.nodes import check_bottom_lines
from app.engine.tactics import TacticContext, select_tactic

logger = logging.getLogger(__name__)

AGENT_TACTIC_HINT = (
    "anchoring(锚定), concession(让步), divide_conquer(分而治之), good_cop_bad_cop(红白脸), "
    "scarcity(稀缺施压), silence(沉默施压), carrot_stick(胡萝卜加大棒), other(试探)"
)

AGENT_TOOL_CALL_LIMIT = 10  # 单轮工具调用上限（防死循环/无效往返）

AGENT_SYSTEM_PROMPT = """你是资深谈判对手，正在和用户进行一场 {scenario_title} 谈判。请按以下工作流完成每一轮回应：

【你的角色】
{opponent_role}

【当前局势】
- 轮次：第 {round} 轮（阶段：{phase}）
- 已用战术：{used_tactics}
- 出价记录：{offers}

【工作流程（每轮必须按顺序执行）】
1. 先调用 read_current_state 查看完整谈判状态（历史对话等）
2. 可选：调用 analyze_user_intent 确认用户意图
3. 可选：调用 select_tactic_by_rules 获取规则推荐的战术，也可自行从 {tactic_hint} 中挑选
4. 若用户话术与历史诉求相似（讨价还价/施压/询问底线），先调用 search_memory 参考往期对手的应答风格与报价口径
5. 组织你的回应：以角色身份说话，保持战术一致性，回复中必须给出明确数值（如「报价：XX 万」「付款周期：XX 天」）。用户说过的话不必复述，直接针对内容回应
6. 必须调用 validate_reply 校验你的回应是否符合底线；若有违规，修改回应后再次校验，直到通过
7. 全部通过后，直接输出最终回应文本（不要再调用任何工具）

【对话历史】
{history}
【本轮用户发言】
用户说：{user_msg}

直接输出你的回应即可，不要解释。"""


class AgentStateBox:
    """闭包状态容器：每轮 run_round 前更新，供 Tools 读取。"""

    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.rag = None


def build_agent_tools(box: AgentStateBox) -> list[Any]:
    """构造 Agent Tools（规则能力工具化，闭包读取当前轮状态）。"""

    @tool
    def read_current_state() -> str:
        """查看当前谈判完整状态（历史对话、轮次、出价、已用战术等），返回 JSON。"""
        s = box.state
        return json.dumps(
            {
                "round": s.get("round", 1),
                "phase": s.get("phase", "opening"),
                "history": [
                    {"role": m.get("role"), "content": str(m.get("content", ""))[:200]}
                    for m in (s.get("history") or [])[-8:]
                ],
                "used_tactics": s.get("used_tactics") or [],
                "offers": s.get("offers_json") or [],
                "user_message": s.get("user_message", ""),
            },
            ensure_ascii=False,
        )

    @tool
    def analyze_user_intent(user_msg: str) -> str:
        """分析用户这句发言的意图（规则引擎）：返回 intent_type/price/emotion 等 JSON。"""
        return json.dumps(rule_intent(user_msg), ensure_ascii=False)

    @tool
    def select_tactic_by_rules() -> str:
        """按规则库推荐战术：返回战术名与理由（也可不采纳，自行选择）。"""
        s = box.state
        intent = s.get("intent") or {}
        firmness = (
            "low"
            if intent.get("concessions")
            else "high"
            if intent.get("intent_type") in ("reject", "offer")
            else "low"
        )
        ctx = TacticContext(
            phase=s.get("phase", "opening"),
            round=s.get("round", 1),
            scenario=s.get("scenario") or {},
            user_intent=intent,
            user_concede_count=s.get("user_concede_count", 0),
            user_firmness=firmness,
            last_user_msg_length=len(s.get("user_message", "")),
            rounds_since_last_progress=s.get("rounds_since_last_progress", 0),
            used_tactics=s.get("used_tactics") or [],
            tactic_context=s.get("tactic_context") or {},
        )
        decision = select_tactic(ctx)
        return json.dumps(
            {"tactic": decision.name, "reason": decision.reason},
            ensure_ascii=False,
        )

    @tool
    def search_memory(query: str) -> str:
        """检索记忆库中相似情境下对手的应答（跨会话经验），返回文本片段列表。"""
        rag = box.rag
        if rag is None:
            return "（暂无可用记忆）"
        try:
            refs = rag.search(
                (box.state.get("scenario_id") or ""),
                query,
                top_k=3,
                role="assistant",
            )
            refs = [r for r in refs if r.get("role") == "assistant"]
            logger.info("Agent 调用 search_memory query=%r → %d 条", query[:50], len(refs))
            return (
                "\n".join(f"- {r['text']}" for r in refs if r.get("text"))
                or "（暂无相似记忆）"
            )
        except Exception as exc:  # noqa: BLE001 RAG 故障不阻断
            logger.warning("Agent RAG 检索失败: %s", exc)
            return "（记忆检索暂不可用）"

    @tool
    def validate_reply(reply: str) -> str:
        """底线校验：检查你拟定的回应是否越过场景底线（数值越界）。返回违规列表，空列表=通过。"""
        violations = check_bottom_lines(reply, box.state.get("scenario") or {})
        return json.dumps(violations, ensure_ascii=False)

    return [read_current_state, analyze_user_intent, select_tactic_by_rules, search_memory, validate_reply]


def build_agent(
    llm: BaseLLM,
    *,
    checkpointer: Any | None = None,
    rag: Any | None = None,
) -> tuple[Any, AgentStateBox]:
    """构建 ReAct Agent 图（create_agent，官方 API）。

    Source: https://reference.langchain.com/python/langchain/agents/factory/create_agent
    - ToolCallLimitMiddleware：单轮工具调用上限 10 次，防 LLM 死循环/无效往返拖慢响应
      （超限默认 continue：错误回传 LLM 促其直接输出，异常由引擎 fallback 兜底）。
    """
    from langchain.agents.middleware import ToolCallLimitMiddleware

    box = AgentStateBox()
    box.rag = rag
    model = getattr(llm, "model", None)
    if model is None:
        raise ValueError("Agent 模式需要模型实例（OpenAIClient.model）")
    graph = create_agent(
        model=model,
        tools=build_agent_tools(box),
        middleware=[ToolCallLimitMiddleware(run_limit=AGENT_TOOL_CALL_LIMIT)],
        checkpointer=checkpointer,
        name="negotiation_agent",
    )
    return graph, box


def build_agent_system_prompt(state: dict[str, Any]) -> str:
    """按当前状态组装动态 system prompt（对手人设/战术/历史/本轮发言）。"""
    scenario = state.get("scenario") or {}
    history = "\n".join(
        f"{'你' if m.get('role') == 'assistant' else '对方'}: {str(m.get('content', ''))[:120]}"
        for m in (state.get("history") or [])[-8:]
    ) or "（尚未有对话）"
    return AGENT_SYSTEM_PROMPT.format(
        scenario_title=scenario.get("title", "商务谈判"),
        opponent_role=scenario.get("opponent_role", "你是谈判对手。"),
        round=state.get("round", 1),
        phase=state.get("phase", "opening"),
        used_tactics="、".join(state.get("used_tactics") or []) or "（无）",
        offers=" → ".join(
            str(o.get("numbers")) for o in (state.get("offers_json") or []) if o.get("numbers") is not None
        )
        or "（暂无报价）",
        tactic_hint=AGENT_TACTIC_HINT,
        history=history,
        user_msg=state.get("user_message", ""),
    )


def extract_agent_reply(result: dict[str, Any]) -> str:
    """从 create_agent 输出中提取最终 AI 回复文本（最后一条 AIMessage.content）。"""
    messages = result.get("messages") or []
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "ai":
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("text")]
                return "".join(parts).strip()
    raise ValueError("Agent 未产出回复文本")


def first_offer_numbers(reply: str) -> float | None:
    """从回复中提取报价数字（供 offers_json 记录）。"""
    return first_price(reply)
