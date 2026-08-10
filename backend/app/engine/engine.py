"""谈判引擎门面：单轮驱动的完整状态机，供 WebSocket 路由层调用。"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.engine.llm import BaseLLM, GLMClient, MockLLM
from app.engine.nodes import build_graph

logger = logging.getLogger(__name__)


def build_llm() -> BaseLLM:
    """按配置构造 LLM：有 key 用 GLM，否则 Mock（无 key 全功能可跑）。"""
    settings = get_settings()
    if settings.llm_api_key:
        try:
            return GLMClient(settings)
        except ValueError as exc:
            logger.warning("GLM 客户端初始化失败，降级 MockLLM: %s", exc)
    return MockLLM()


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
        self.graph = build_graph(self.llm, checkpointer=checkpointer, rag=rag, stream=stream_callback)

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
        """执行一轮完整谈判（意图→战术→话术→底线检查→重试），返回更新后状态。

        thread_id 提供时将本轮最终状态写入 checkpointer（PRD 9.13）。
        """
        if not user_message.strip():
            raise ValueError("用户消息不能为空")
        inputs = {
            **state,
            "user_message": user_message.strip(),
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
        if thread_id and self.checkpointer is not None:
            await self.graph.aupdate_state(
                config,
                {
                    "history": result.get("history") or [],
                    "offers_json": result.get("offers_json") or [],
                    "round": result.get("round", 1),
                    "last_offer": result.get("last_offer"),
                    "user_concede_count": result.get("user_concede_count", 0),
                    "rounds_since_last_progress": result.get("rounds_since_last_progress", 0),
                    "used_tactics": result.get("used_tactics") or [],
                },
            )
        return result

    async def restore_state(self, thread_id: str) -> dict[str, Any] | None:
        """从 checkpointer 恢复最新完整状态；无记录或无 checkpointer 返回 None。"""
        if self.checkpointer is None:
            return None
        config = {"configurable": {"thread_id": thread_id}}
        snap = await self.graph.aget_state(config)
        return dict(snap.values) if snap is not None else None
