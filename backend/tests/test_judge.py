"""LLM-as-Judge 主观评分测试（PRD 9.9）：4 维度 1-5 分、钳制、解析失败兜底、默认接线。"""

from app.engine.llm import MockLLM
from app.services.judge import (
    DIMENSION_KEYS,
    LLMJudge,
    build_judge,
    default_judge,
)


class BadLLM(MockLLM):
    """每次都抛异常的 LLM，用于验证兜底路径。"""

    async def ainvoke(self, prompt: str, *, light: bool = False) -> str:
        raise RuntimeError("gateway down")


class OutOfRangeLLM(MockLLM):
    """返回越界分数的 LLM。"""

    async def ainvoke(self, prompt: str, *, light: bool = False) -> str:
        return '{"naturalness": 9, "strategy_diversity": -2, "emotion_control": 5, "logic_consistency": 1}'



class PartialLLM(MockLLM):
    """只返回部分维度，验证缺省回退。"""

    async def ainvoke(self, prompt: str, *, light: bool = False) -> str:
        return '{"naturalness": 5}'


HISTORY = [
    {"role": "user", "content": "太贵了，200 万"},
    {"role": "assistant", "content": "200 万可以谈，但保修期要缩短。"},
    {"role": "user", "content": "那 180 万，保修 2 年"},
    {"role": "assistant", "content": "180 万太低，最多 190 万。"},
]

SCENARIO = {"title": "IT 采购谈判", "briefing": "采购高性能服务器，预算有限。"}


class TestLLMJudge:
    async def test_mock_llm_returns_all_dimensions(self):
        result = await LLMJudge(MockLLM())(HISTORY, SCENARIO)
        for key in DIMENSION_KEYS:
            assert key in result, f"缺少维度 {key}"
            assert 1 <= float(result[key]) <= 5
        assert isinstance(result["weak_points"], list) and result["weak_points"]
        assert isinstance(result["advice"], str) and result["advice"].strip()

    async def test_out_of_range_scores_are_clamped(self):
        result = await LLMJudge(OutOfRangeLLM())(HISTORY, SCENARIO)
        assert result["naturalness"] == 5.0
        assert result["strategy_diversity"] == 1.0
        assert result["emotion_control"] == 5.0
        assert result["logic_consistency"] == 1.0

    async def test_missing_dimensions_fallback_to_default(self):
        result = await LLMJudge(PartialLLM())(HISTORY, SCENARIO)
        assert result["naturalness"] == 5.0
        for key in ("strategy_diversity", "emotion_control", "logic_consistency"):
            assert result[key] == 3.0

    async def test_llm_failure_falls_back_to_default_judge(self):
        result = await LLMJudge(BadLLM())(HISTORY, SCENARIO)
        default = await default_judge(HISTORY, SCENARIO)
        assert result == default

    async def test_garbage_output_falls_back(self):
        class GarbageLLM(MockLLM):
            async def ainvoke(self, prompt: str, *, light: bool = False) -> str:
                return "我不知道你在说什么"

        result = await LLMJudge(GarbageLLM())(HISTORY, SCENARIO)
        assert result["naturalness"] == 3.0

    async def test_build_judge_uses_engine_llm(self):
        judge = build_judge()
        assert isinstance(judge, LLMJudge)


class TestDefaultJudge:
    async def test_neutral_scores_and_advice(self):
        result = await default_judge(HISTORY, SCENARIO)
        for key in DIMENSION_KEYS:
            assert result[key] == 3.0
        assert result["weak_points"]
        assert result["advice"]
