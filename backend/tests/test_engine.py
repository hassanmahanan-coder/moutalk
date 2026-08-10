"""谈判引擎闭环测试：一轮完整谈判、底线重试循环、兜底模板。"""


import pytest

from app.engine.engine import NegotiationEngine
from app.engine.llm import MockLLM
from app.engine.nodes import MAX_RETRY, check_bottom_lines
from app.scenarios import load_scenario


class FakeLLM(MockLLM):
    """确定性话术：utterance 按脚本顺序返回，其余委托 MockLLM。"""

    configured = True

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.utterance_calls = 0
        self.intent_calls = 0

    async def ainvoke(self, prompt: str, *, light: bool = False) -> str:
        if "[意图提取]" in prompt:
            self.intent_calls += 1
            return await super().ainvoke(prompt, light=light)
        if "[战术兜底]" in prompt or "[复盘评估]" in prompt:
            return await super().ainvoke(prompt, light=light)
        idx = min(self.utterance_calls, len(self.replies) - 1)
        self.utterance_calls += 1
        return self.replies[idx]


@pytest.fixture
def scenario():
    return load_scenario("it_procurement")


@pytest.fixture
def engine(scenario):
    return NegotiationEngine(scenario, llm=FakeLLM([]))


class TestOpening:
    def test_opening_line_present(self, engine):
        assert "235" in engine.opening_line()

    def test_initial_state(self, engine):
        s = engine.initial_state("s1")
        assert s["round"] == 1
        assert s["history"] == []
        assert s["scenario_id"] == "it_procurement"


class TestFullRound:
    async def test_round_passes_and_advances(self, scenario):
        eng = NegotiationEngine(scenario, llm=FakeLLM(["报价：185 万，付款周期：60 天。"]))
        s = eng.initial_state("s1")
        s = await eng.run_round(s, "报价 200 万可以吗？")
        assert s["bottom_line_status"] == "ok"
        assert s["reply"] == "报价：185 万，付款周期：60 天。"
        assert s["round"] == 2
        assert len(s["history"]) == 2
        assert s["history"][0]["role"] == "user"
        assert s["history"][1]["role"] == "assistant"
        assert s["intent"]["intent_type"] == "offer"
        assert s["intent"]["price"] == 200
        assert s["offers_json"], "应有报价记录"

    async def test_mock_llm_no_key_full_round(self, scenario):
        eng = NegotiationEngine(scenario, llm=MockLLM())
        s = eng.initial_state("s2")
        s = await eng.run_round(s, "200 万可以吗，如果行今天就签")
        assert s["bottom_line_status"] == "ok"
        assert s["reply"]
        assert s["round"] == 2

    async def test_used_tactics_recorded(self, scenario):
        eng = NegotiationEngine(scenario, llm=FakeLLM(["报价：185 万。"]))
        s = eng.initial_state("s3")
        s["round"] = 2  # 核心阶段才触发虚假底线规则
        s = await eng.run_round(s, "太贵了")
        assert s["used_tactics"][-1] == "false_bottom"  # 攻击性强 → 虚假底线

    async def test_history_message_carries_tactic_and_bottom_line(self, scenario):
        """回放/战术统计的数据源：assistant 消息必须带 tactic 与底线状态字段。"""
        eng = NegotiationEngine(scenario, llm=FakeLLM(["报价：185 万。"]))
        s = eng.initial_state("s6")
        s["round"] = 2
        s = await eng.run_round(s, "太贵了")
        assert len(s["history"]) == 2
        assistant = s["history"][1]
        assert assistant["role"] == "assistant"
        assert assistant["tactic"] == "false_bottom"
        assert assistant["bottom_line_status"] == "ok"

    async def test_true_streaming_callback_receives_full_reply(self, scenario):
        """真流式（PRD 9.4 阶段 2）：stream callback 收到的片段拼接 == 最终 reply。"""
        collected: list[str] = []

        async def stream(piece: str) -> None:
            collected.append(piece)

        eng = NegotiationEngine(
            scenario,
            llm=FakeLLM(["报价：185 万，付款周期：60 天。"]),
            stream_callback=stream,
        )
        s = eng.initial_state("s7")
        s = await eng.run_round(s, "报价 200 万可以吗？")
        assert collected, "流式应产出至少一片"
        assert "".join(collected) == s["reply"]
        assert s["bottom_line_status"] == "ok"  # 流式不破坏底线检查

    async def test_streaming_retry_uses_non_stream_path(self, scenario):
        """重试轮（retry_count>0）不流式（避免已展示文本残影）。"""
        collected: list[str] = []

        async def stream(piece: str) -> None:
            collected.append(piece)

        eng = NegotiationEngine(
            scenario,
            llm=FakeLLM(["报价：170 万", "报价：185 万"]),
            stream_callback=stream,
        )
        s = eng.initial_state("s8")
        s = await eng.run_round(s, "报价 200 万")
        assert collected, "首轮正常流式"
        assert s["retry_count"] == 1


class TestBottomLineRetry:
    async def test_retry_then_pass(self, scenario):
        eng = NegotiationEngine(
            scenario, llm=FakeLLM(["报价：170 万", "报价：175 万", "报价：185 万"])
        )
        s = eng.initial_state("s4")
        s = await eng.run_round(s, "报价 200 万")
        assert s["bottom_line_status"] == "ok"
        assert s["reply"] == "报价：185 万"
        assert s["retry_count"] == 2  # 两次被驳回后通过

    async def test_fallback_after_max_retries(self, scenario):
        bad = ["报价：170 万"] * (MAX_RETRY + 1)
        eng = NegotiationEngine(scenario, llm=FakeLLM(bad))
        s = eng.initial_state("s5")
        s = await eng.run_round(s, "报价 200 万")
        assert s["bottom_line_status"] == "fallback"
        assert s["reply_blocked"] is False
        assert s["reply"] in scenario["safe_fallback"]
        assert s["retry_count"] == MAX_RETRY + 1


class TestBottomLineChecker:
    def test_price_below_floor_violation(self, scenario):
        violations = check_bottom_lines("报价：170 万", scenario)
        assert any("价格" in v or "总价" in v for v in violations)

    def test_price_at_floor_ok(self, scenario):
        assert check_bottom_lines("报价：180 万", scenario) == []

    def test_payment_cycle_above_cap_violation(self, scenario):
        violations = check_bottom_lines("报价：200 万，付款周期：120 天", scenario)
        assert any("付款" in v for v in violations)

    def test_no_number_no_violation(self, scenario):
        assert check_bottom_lines("这个价格我们再谈谈", scenario) == []

    def test_chinese_number_price(self, scenario):
        violations = check_bottom_lines("报价：一百七十万", scenario)
        assert any("价" in v for v in violations)


class TestScenarios:
    def test_all_scenarios_load_and_valid(self):
        for sid in ("it_procurement", "salary", "supplier"):
            data = load_scenario(sid)
            assert data["id"] == sid
            assert data["opening_line"]
            assert data["safe_fallback"]

    def test_salary_ceiling_direction(self):
        scenario = load_scenario("salary")
        violations = check_bottom_lines("底薪：4 万", scenario)
        assert any("底薪" in v for v in violations)
        assert check_bottom_lines("底薪：3.2 万", scenario) == []
