"""ReAct Agent 引擎测试（langchain.agents.create_agent 双模式）。

- 无 key（MockLLM）→ 工作流模式（agent_mode=False）
- 有 key（FakeLLM.configured=True）→ Agent 模式（agent_mode=True）
- Agent 底线双校验：回复越底线 → fallback 模板；通过 → opponent_offer 提取报价
"""

import json

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from app.engine.agent_builder import build_agent, build_agent_tools, extract_agent_reply
from app.engine.engine import NegotiationEngine
from app.engine.llm import BaseLLM
from app.scenarios import load_scenario


class FakeLLM(BaseLLM):
    """configured=True 的假 LLM：暴露真实 ChatOpenAI 实例供 create_agent 绑定。"""

    configured = True

    def __init__(self):
        self._llm = ChatOpenAI(
            base_url="http://localhost:9999/v1",
            api_key="fake-key",
            model="deepseek-v4-flash",
        )

    @property
    def model(self):
        return self._llm

    async def ainvoke(self, prompt, *, light=False):
        return "报价：188 万。"

    async def astream(self, prompt, *, light=False):
        yield "报价：188 万。"


def _state():
    return {
        "session_id": "t1",
        "scenario_id": "it_procurement",
        "scenario": load_scenario("it_procurement"),
        "round": 1,
        "phase": "opening",
        "history": [],
        "used_tactics": [],
        "offers_json": [],
        "user_concede_count": 0,
        "rounds_since_last_progress": 0,
    }


class TestDualMode:
    def test_mock_llm_uses_workflow_mode(self):
        engine = NegotiationEngine(load_scenario("it_procurement"), llm=_MockLLM())
        assert engine.agent_mode is False

    def test_configured_llm_uses_agent_mode(self):
        engine = NegotiationEngine(load_scenario("it_procurement"), llm=FakeLLM())
        assert engine.agent_mode is True

    def test_agent_graph_is_compiled(self):
        llm = FakeLLM()
        graph, box = build_agent(llm, checkpointer=None, rag=None)
        assert box is not None
        assert hasattr(graph, "ainvoke")


class _MockLLM(BaseLLM):
    configured = False

    async def ainvoke(self, prompt, *, light=False):
        return "报价：188 万。"

    async def astream(self, prompt, *, light=False):
        yield "报价：188 万。"


class TestAgentTools:
    def test_analyze_user_intent_rule(self):
        from app.engine.agent_builder import AgentStateBox

        box = AgentStateBox()
        box.state = {"user_message": "235 万太贵了，200 万可以吗"}
        tools = {t.name: t for t in build_agent_tools(box)}
        out = json.loads(tools["analyze_user_intent"].func("235 万太贵了，200 万可以吗"))
        assert out["intent_type"] == "offer"
        assert out["price"] == 235 or out["price"] == 200

    def test_validate_reply_rule(self):
        from app.engine.agent_builder import AgentStateBox

        box = AgentStateBox()
        box.state = {"scenario": load_scenario("it_procurement")}
        tools = {t.name: t for t in build_agent_tools(box)}
        assert tools["validate_reply"].func("报价：150 万") != "[]"  # 低于底线 180 → 违规
        assert tools["validate_reply"].func("报价：188 万，付款周期 60 天") == "[]"

    def test_read_state_returns_json(self):
        from app.engine.agent_builder import AgentStateBox

        box = AgentStateBox()
        box.state = _state()
        tools = {t.name: t for t in build_agent_tools(box)}
        data = json.loads(tools["read_current_state"].func())
        assert data["round"] == 1
        assert data["user_message"] == ""


class TestAgentRound:
    async def test_agent_reply_passes_bottom_line(self, monkeypatch):
        engine = NegotiationEngine(load_scenario("it_procurement"), llm=FakeLLM())
        engine.agent_mode = True

        async def fake_ainvoke(inputs, config=None):
            return {"messages": [AIMessage(content="可以谈，报价：188 万，包含全部服务。")]}

        monkeypatch.setattr(engine.graph, "ainvoke", fake_ainvoke)
        state = engine.initial_state("t1")
        out = await engine.run_round(state, "报价 200 万可以吗？")
        assert out["reply"] == "可以谈，报价：188 万，包含全部服务。"
        assert out["bottom_line_status"] == "ok"
        assert out["opponent_offer"]["numbers"] == 188
        assert out["round"] == 2
        assert len(out["history"]) == 2

    async def test_agent_reply_breaks_bottom_line_uses_fallback(self, monkeypatch):
        engine = NegotiationEngine(load_scenario("it_procurement"), llm=FakeLLM())
        engine.agent_mode = True

        async def fake_ainvoke(inputs, config=None):
            return {"messages": [AIMessage(content="同意，150 万就可以。")]}  # 低于底线 180

        monkeypatch.setattr(engine.graph, "ainvoke", fake_ainvoke)
        state = engine.initial_state("t1")
        out = await engine.run_round(state, "便宜点可以吗？")
        assert out["bottom_line_status"] == "fallback"
        assert out["reply"] != "同意，150 万就可以。"
        assert out["opponent_offer"] is None

    async def test_agent_exception_uses_fallback(self, monkeypatch):
        engine = NegotiationEngine(load_scenario("it_procurement"), llm=FakeLLM())
        engine.agent_mode = True

        async def fake_ainvoke(inputs, config=None):
            raise RuntimeError("gateway down")

        monkeypatch.setattr(engine.graph, "ainvoke", fake_ainvoke)
        state = engine.initial_state("t1")
        out = await engine.run_round(state, "在吗？")
        assert out["bottom_line_status"] == "fallback"
        assert out["reply"]

    async def test_agent_round_rate_limited_skips_llm(self, monkeypatch):
        """Bug：Agent 循环直调 LLM 绕过 per-call 限流 → 轮级限流，超限不调 LLM、返回降级话术。"""

        called = {"n": 0}

        async def fake_ainvoke(inputs, config=None):
            called["n"] += 1
            return {"messages": [AIMessage(content="正常回复。")]}

        monkeypatch.setattr("app.engine.llm._check_rate_limit", lambda: False)
        engine = NegotiationEngine(load_scenario("it_procurement"), llm=FakeLLM())
        engine.agent_mode = True
        monkeypatch.setattr(engine.graph, "ainvoke", fake_ainvoke)
        state = engine.initial_state("t1")
        out = await engine.run_round(state, "在吗？")
        assert called["n"] == 0, "限流时不应对 LLM 发起调用"
        assert "系统繁忙" in out["reply"]
        assert out["bottom_line_status"] == "fallback"

    async def test_agent_round_updates_tactic_context(self, monkeypatch):
        """Bug B：Agent 补齐战术后应更新 tactic_context（多步战术跟踪）。"""
        engine = NegotiationEngine(load_scenario("it_procurement"), llm=FakeLLM())
        engine.agent_mode = True

        async def fake_ainvoke(inputs, config=None):
            return {"messages": [AIMessage(content="可以谈，报价：188 万，包含全部服务。")]}

        monkeypatch.setattr(engine.graph, "ainvoke", fake_ainvoke)
        state = engine.initial_state("t1")
        out = await engine.run_round(state, "235 万太贵了，能降到 200 万吗？")
        assert out.get("tactic_context") is not None, "应维护 tactic_context"
        assert "active_tactic" in out["tactic_context"]
        assert "step" in out["tactic_context"]

    def test_extract_agent_reply(self):
        result = {"messages": [AIMessage(content="最终话术。")]}
        assert extract_agent_reply(result) == "最终话术。"


class TestAgentFixes:
    async def test_agent_mode_restore_state_returns_none(self, monkeypatch):
        """Bug A：Agent 图状态是 messages，不得冒充 NegotiationState（断线续谈走业务表）。"""
        engine = NegotiationEngine(load_scenario("it_procurement"), llm=FakeLLM())
        engine.agent_mode = True

        async def fake_aget_state(config):
            from typing import ClassVar

            class _Snap:
                values: ClassVar[dict] = {"messages": [{"type": "ai", "content": "x"}]}

            return _Snap()

        monkeypatch.setattr(engine.graph, "aget_state", fake_aget_state)
        assert await engine.restore_state("t1") is None

    async def test_agent_round_sets_intent_and_tactic(self, monkeypatch):
        """Bug B：Agent 回复后需补 intent/selected_tactic，保证 meta 战术标签与报告统计。"""
        engine = NegotiationEngine(load_scenario("it_procurement"), llm=FakeLLM())
        engine.agent_mode = True

        async def fake_ainvoke(inputs, config=None):
            return {"messages": [AIMessage(content="可以谈，报价：188 万，包含全部服务。")]}

        monkeypatch.setattr(engine.graph, "ainvoke", fake_ainvoke)
        state = engine.initial_state("t1")
        out = await engine.run_round(state, "235 万太贵了，能降到 200 万吗？")
        assert out.get("intent", {}).get("intent_type") == "offer", "应补意图"
        assert out.get("selected_tactic"), "应补战术"
        assistant_msgs = [m for m in out.get("history", []) if m.get("role") == "assistant"]
        assert assistant_msgs and assistant_msgs[0].get("tactic") == out["selected_tactic"]
        assert out.get("used_tactics") == [out["selected_tactic"]], "应记录已用战术"

    def test_payment_cycle_not_misread_as_delivery(self):
        """Bug C：delivery 关键词'天'歧义——'付款 60 天'不得被判为交期 60 天违规。"""
        from app.engine.nodes import check_bottom_lines

        scenario = load_scenario("it_procurement")
        assert check_bottom_lines("付款 60 天，交期 15 天", scenario) == []
        assert check_bottom_lines("付款周期 60 天", scenario) == []

    def test_select_tactic_tool_uses_firmness(self):
        """Bug D：Agent 战术工具需感知用户坚定度（让步词 → firmness low）。"""
        from app.engine.agent_builder import AgentStateBox, build_agent_tools

        box = AgentStateBox()
        box.state = {
            "scenario": load_scenario("it_procurement"),
            "round": 2,
            "phase": "core",
            "user_message": "可以接受，但希望再优惠一点",
            "intent": {"concessions": ["可以接受"]},
            "user_concede_count": 0,
            "rounds_since_last_progress": 0,
            "used_tactics": [],
            "tactic_context": {},
        }
        tools = {t.name: t for t in build_agent_tools(box)}
        out = json.loads(tools["select_tactic_by_rules"].func())
        assert out["tactic"], "应返回战术推荐"
