"""PostgresSaver 状态持久化测试：checkpointer 落库、thread_id 恢复、跨引擎重建。"""

import uuid

import pytest

from app.engine import checkpointer as cp
from app.engine.engine import NegotiationEngine
from app.engine.llm import MockLLM
from app.engine.nodes import build_graph
from app.scenarios import load_scenario


class FakeLLM(MockLLM):
    """确定性话术，utterance 按脚本返回。"""

    configured = True

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls = 0

    async def ainvoke(self, prompt: str, *, light: bool = False) -> str:
        if "[意图提取]" in prompt:
            return await super().ainvoke(prompt, light=light)
        if "[战术兜底]" in prompt or "[复盘评估]" in prompt:
            return await super().ainvoke(prompt, light=light)
        idx = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return self.replies[idx]


@pytest.fixture
def scenario():
    return load_scenario("it_procurement")


def test_checkpointer_uri_uses_test_db():
    uri = cp.get_checkpointer_uri()
    assert "moutalk_test" in uri


@pytest.mark.asyncio
async def test_checkpoint_persists_and_restores_state(scenario):
    thread_id = str(uuid.uuid4())
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from app.engine.checkpointer import open_checkpointer

    async with open_checkpointer() as checkpointer:
        assert isinstance(checkpointer, AsyncPostgresSaver)
        assert checkpointer is not None
        graph = build_graph(FakeLLM(["报价：185 万，付款周期：60 天。"]), checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        state = NegotiationEngine(scenario, llm=FakeLLM([])).initial_state(thread_id)
        state["user_message"] = "报价 200 万可以吗？"
        result = await graph.ainvoke(state, config=config)
        assert result["history"] or result["reply"], "一轮应产生回复"

        snap = await graph.aget_state(config)
        assert snap is not None
        values = snap.values
        assert values["user_message"] == "报价 200 万可以吗？"


@pytest.mark.asyncio
async def test_checkpoint_threads_are_isolated(scenario):
    from app.engine.checkpointer import open_checkpointer

    async with open_checkpointer() as checkpointer:
        g1 = build_graph(FakeLLM(["报价：185 万。"]), checkpointer=checkpointer)
        g2 = build_graph(FakeLLM(["报价：185 万。"]), checkpointer=checkpointer)
        c1 = {"configurable": {"thread_id": str(uuid.uuid4())}}
        c2 = {"configurable": {"thread_id": str(uuid.uuid4())}}

        s1 = NegotiationEngine(scenario, llm=FakeLLM([])).initial_state("a")
        s1["user_message"] = "200 万行吗"
        await g1.ainvoke(s1, config=c1)

        s2 = NegotiationEngine(scenario, llm=FakeLLM([])).initial_state("b")
        s2["user_message"] = "180 万吧"
        await g2.ainvoke(s2, config=c2)

        snap1 = await g1.aget_state(c1)
        snap2 = await g2.aget_state(c2)
        assert snap1.values["user_message"] == "200 万行吗"
        assert snap2.values["user_message"] == "180 万吧"


@pytest.mark.asyncio
async def test_missing_thread_returns_none_state(scenario):
    from app.engine.checkpointer import open_checkpointer

    async with open_checkpointer() as checkpointer:
        graph = build_graph(FakeLLM(["报价：185 万。"]), checkpointer=checkpointer)
        snap = await graph.aget_state({"configurable": {"thread_id": str(uuid.uuid4())}})
        assert snap is not None
        assert snap.values == {} or not snap.values


@pytest.mark.asyncio
async def test_engine_run_round_persists_full_state(scenario):
    """engine.run_round(thread_id=) 把 finalize 后完整状态写入 checkpoint，
    restore_state 可恢复出含 history 的完整状态（WS 断线恢复路径，PRD 9.13）。"""
    from app.engine.checkpointer import open_checkpointer

    thread_id = str(uuid.uuid4())
    async with open_checkpointer() as checkpointer:
        engine = NegotiationEngine(scenario, llm=FakeLLM(["报价：185 万，付款周期：60 天。"]), checkpointer=checkpointer)
        state = engine.initial_state(thread_id)
        result = await engine.run_round(state, "报价 200 万可以吗？", thread_id=thread_id)
        assert result["history"], "一轮后应有历史"

        restored = await engine.restore_state(thread_id)
        assert restored is not None
        assert restored["history"] == result["history"]
        assert restored["round"] == result["round"]
        assert restored["user_message"] == "报价 200 万可以吗？"

        second = await engine.run_round(restored, "再低点，180 万", thread_id=thread_id)
        assert len(second["history"]) > len(result["history"]), "第二轮历史应更长"
