"""谈判引擎门面：单轮驱动的完整状态机，供 WebSocket 路由层调用。

双模式（ReAct Agent / 工作流）：
- 有 LLM key（configured=True）→ langchain.agents.create_agent ReAct 图
  （Source: https://reference.langchain.com/python/langchain/agents/factory/create_agent）
- 无 key → 原 5 节点确定性工作流（MockLLM 可离线全功能跑）
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from app.core.config import get_settings
from app.engine.llm import BaseLLM, MockLLM, OpenAIClient
from app.engine.nodes import check_bottom_lines

logger = logging.getLogger(__name__)


def build_llm() -> BaseLLM:
    """按配置构造 LLM：有 key 用 OpenAI 兼容网关，否则 Mock（无 key 全功能可跑）。"""
    settings = get_settings()
    if settings.llm_api_key:
        try:
            return OpenAIClient(settings)
        except ValueError as exc:
            logger.warning("OpenAI 兼容客户端初始化失败，降级 MockLLM: %s", exc)
    return MockLLM()


def _config_if(thread_id: str | None, checkpointer: Any) -> Any:
    """thread + checkpointer 可用时返回 LangGraph config，否则 None。"""
    if thread_id and checkpointer is not None:
        return {"configurable": {"thread_id": thread_id}}
    return None


class NegotiationEngine:
    def __init__(
        self,
        scenario: dict[str, Any],
        llm: BaseLLM | None = None,
        checkpointer: Any | None = None,
        rag: Any | None = None,
        stream_callback: Any | None = None,
    ):
        self.scenario = scenario
        self.llm = llm or build_llm()
        self.checkpointer = checkpointer
        self.rag = rag
        self.stream_callback = stream_callback
        self._agent_box = None
        if self.llm.configured:
            from app.engine.agent_builder import build_agent

            try:
                self.graph, self._agent_box = build_agent(
                    self.llm, checkpointer=checkpointer, rag=rag
                )
                self.agent_mode = True
            except Exception as exc:  # noqa: BLE001 Agent 构建失败降级工作流
                logger.warning("Agent 构建失败，降级工作流模式: %s", exc)
                self._init_workflow_graph()
        else:
            self._init_workflow_graph()

    def _init_workflow_graph(self) -> None:
        """初始化 5 节点确定性工作流（Mock/无 key 模式）。"""
        from app.engine.nodes import build_graph

        self.agent_mode = False
        self.graph = build_graph(
            self.llm, checkpointer=self.checkpointer, rag=self.rag, stream=self.stream_callback
        )

    def initial_state(self, session_id: str = "") -> dict:
        return {
            "session_id": session_id,
            "scenario_id": self.scenario.get("id", ""),
            "scenario": self.scenario,
            "round": 1,
            "phase": "opening",
            "history": [],
            "intent": {},
            "selected_tactic": "",
            "tactic_reason": "",
            "tactic_sub_role": None,
            "tactic_context": {},
            "used_tactics": [],
            "opponent_offer": None,
            "last_offer": None,
            "offers_json": [],
            "retry_count": 0,
            "retry_reason": None,
            "reply": None,
            "reply_blocked": False,
            "bottom_line_status": "",
            "user_concede_count": 0,
            "rounds_since_last_progress": 0,
            "meta": {},
        }

    def opening_line(self) -> str:
        """AI 开场白（场景包配置）。"""
        return self.scenario.get("opening_line", "")

    def _finalize_round(self, state: dict) -> dict:
        """图执行完成后更新会话级状态：历史、轮次、让步统计、进度。"""
        user_msg = state.get("user_message", "")
        reply = state.get("reply", "")
        history = list(state.get("history") or [])
        history.append({"role": "user", "content": user_msg})
        if reply:
            # tactic/bottom_line_status 持久化到消息：管理后台战术统计与回放标注的数据源
            history.append(
                {
                    "role": "assistant",
                    "content": reply,
                    "tactic": state.get("selected_tactic", ""),
                    "bottom_line_status": state.get("bottom_line_status", ""),
                }
            )
        state["history"] = history
        state["round"] = state.get("round", 1) + 1

        if state.get("opponent_offer"):
            state.setdefault("offers_json", []).append(state["opponent_offer"])
            state["last_offer"] = state["opponent_offer"]

        intent = state.get("intent") or {}
        if intent.get("concessions"):
            state["user_concede_count"] = state.get("user_concede_count", 0) + 1
        # 进度判定：用户给出新报价视为进展
        user_price = intent.get("price")
        last_price = (state.get("last_offer") or {}).get("numbers")
        if user_price is not None and user_price != last_price:
            state["rounds_since_last_progress"] = 0
        else:
            state["rounds_since_last_progress"] = state.get("rounds_since_last_progress", 0) + 1

        tactic = state.get("selected_tactic", "")
        if tactic:
            state.setdefault("used_tactics", []).append(tactic)
        return state

    async def run_round(self, state: dict, user_message: str, *, thread_id: str | None = None) -> dict:
        """执行一轮完整谈判，返回更新后状态（Agent 模式或工作流模式）。

        thread_id 提供时将本轮最终状态写入 checkpointer（PRD 9.13）。
        """
        if not user_message.strip():
            raise ValueError("用户消息不能为空")
        if self.agent_mode:
            return await self._run_agent_round(state, user_message.strip(), thread_id=thread_id)
        return await self._run_workflow_round(state, user_message.strip(), thread_id=thread_id)

    async def _run_workflow_round(self, state: dict, user_message: str, *, thread_id: str | None = None) -> dict:
        inputs = {
            **state,
            "user_message": user_message,
            "retry_count": 0,
            "retry_reason": None,
            "reply_blocked": False,
            "bottom_line_status": "",
        }
        config = None
        if thread_id and self.checkpointer is not None:
            config = {"configurable": {"thread_id": thread_id}}
            result = await self.graph.ainvoke(inputs, config=config)
        else:
            result = await self.graph.ainvoke(inputs)
        result = self._finalize_round(result)
        await self._persist_state(result, thread_id, config)
        return result

    async def _run_agent_round(self, state: dict, user_message: str, *, thread_id: str | None = None) -> dict:
        """Agent 模式单轮：动态 system prompt + ReAct 循环 + 底线双校验。"""
        from langchain_core.messages import SystemMessage

        from app.engine.agent_builder import (
            build_agent_system_prompt,
            extract_agent_reply,
        )

        # 轮级限流（PRD 9.6）：Agent 循环内多次直调 LLM（不走 OpenAIClient.ainvoke，
        # per-call 限流失效），改在轮入口扣一次——5 轮/分钟/用户。超限返回降级话术。
        from app.engine.llm import _check_rate_limit

        if not _check_rate_limit():
            logger.warning("Agent 轮次触发限流，返回降级话术")
            reply = "【系统繁忙】请稍候再试，当前请求过多。"
            state = {**state, "user_message": user_message, "reply": reply}
            state["bottom_line_status"] = "fallback"
            state["opponent_offer"] = None
            state["retry_count"] = 0
            state["retry_reason"] = None
            state["reply_blocked"] = False
            state = self._finalize_round(state)
            await self._persist_state(state, thread_id, _config_if(thread_id, self.checkpointer))
            return state

        state = {**state, "user_message": user_message}
        if self._agent_box is not None:
            self._agent_box.state = state

        config = _config_if(thread_id, self.checkpointer)
        inputs = {
            "messages": [
                SystemMessage(content=build_agent_system_prompt(state)),
                HumanMessage(content=user_message),
            ]
        }
        try:
            if config is not None:
                result = await self.graph.ainvoke(inputs, config=config)
            else:
                result = await self.graph.ainvoke(inputs)
            reply = extract_agent_reply(result)
        except Exception as exc:  # noqa: BLE001 Agent 异常 → 兜底模板，不阻断谈判
            logger.warning("Agent 轮次异常，使用兜底回复: %s", exc)
            from app.engine.nodes import fallback_node

            fallback = fallback_node(state)
            reply = fallback.get("reply", "")
            state["reply"] = reply
            state["bottom_line_status"] = "fallback"
            state["opponent_offer"] = None
            state["retry_count"] = 0
            state["retry_reason"] = None
            state["reply_blocked"] = False
            state = self._finalize_round(state)
            await self._persist_state(state, thread_id, config)
            return state
        # 底线双校验：图外层规则硬校验（Agent 不听话时的最终防线）
        state["reply"] = reply
        violations = check_bottom_lines(reply, self.scenario)
        if violations:
            logger.warning("Agent 回复越底线（%s），使用兜底模板", "；".join(violations))
            from app.engine.nodes import fallback_node

            fallback = fallback_node(state)
            reply = fallback.get("reply", "")
            state["reply"] = reply
            state["bottom_line_status"] = "fallback"
            state["opponent_offer"] = None
        else:
            state["bottom_line_status"] = "ok"
            from app.engine.extractor import first_price

            state["opponent_offer"] = {"reply": reply, "numbers": first_price(reply)}
        # Agent 未显式记录意图/战术：用规则补齐，保证 meta 战术标签、进度判定与报告统计
        from app.engine.llm import rule_intent

        state["intent"] = rule_intent(user_message)
        from app.engine.tactics import TacticContext, select_tactic

        _ctx = TacticContext(
            phase=state.get("phase", "opening"),
            round=state.get("round", 1),
            scenario=self.scenario,
            user_intent=state["intent"],
            user_concede_count=state.get("user_concede_count", 0),
            user_firmness=(
                "low"
                if state["intent"].get("concessions")
                else "high"
                if state["intent"].get("intent_type") in ("reject", "offer")
                else "low"
            ),
            last_user_msg_length=len(user_message),
            rounds_since_last_progress=state.get("rounds_since_last_progress", 0),
            used_tactics=state.get("used_tactics") or [],
            tactic_context=state.get("tactic_context") or {},
        )
        _decision = select_tactic(_ctx)
        state["selected_tactic"] = _decision.name
        state["tactic_reason"] = _decision.reason
        # 多步战术跟踪（与工作流 tactic_node 一致）：更新 tactic_context，
        # 支撑红白脸等连续战术的分角状态（troubleshooting #62-B）
        from app.engine.tactics import update_tactic_context

        state["tactic_context"] = update_tactic_context(
            state.get("tactic_context") or {}, _decision
        )
        state["retry_count"] = 0
        state["retry_reason"] = None
        state["reply_blocked"] = False
        state = self._finalize_round(state)
        await self._persist_state(state, thread_id, config)
        return state

    async def _persist_state(self, state: dict, thread_id: str | None, config: Any) -> None:
        """工作流/Agent 共用：checkpointer 落库（若可用）。

        Agent 图状态 schema 是 messages，业务字段由 negotiation.save_round JSON 双写
        （Windows 降级路径本就走业务表），故 Agent 模式跳过 aupdate_state。
        """
        if self.agent_mode:
            return
        if thread_id and self.checkpointer is not None and config is not None:
            await self.graph.aupdate_state(
                config,
                {
                    "history": state.get("history") or [],
                    "offers_json": state.get("offers_json") or [],
                    "round": state.get("round", 1),
                    "last_offer": state.get("last_offer"),
                    "user_concede_count": state.get("user_concede_count", 0),
                    "rounds_since_last_progress": state.get("rounds_since_last_progress", 0),
                    "used_tactics": state.get("used_tactics") or [],
                },
            )

    async def restore_state(self, thread_id: str) -> dict[str, Any] | None:
        """从 checkpointer 恢复最新完整状态；无记录或无 checkpointer 返回 None。

        Agent 模式下图状态是 messages（AgentState），与 NegotiationState 结构不同，
        直接返回会破坏断点续谈——返回 None，由调用方走业务表 JSON 重建（Agent 架构
        Bug A 修复）。
        """
        if self.agent_mode or self.checkpointer is None:
            return None
        config = {"configurable": {"thread_id": thread_id}}
        snap = await self.graph.aget_state(config)
        return dict(snap.values) if snap is not None else None
