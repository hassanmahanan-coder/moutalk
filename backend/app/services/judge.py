"""LLM-as-Judge 主观评分（PRD 9.9 / 7.4）：话术自然度 | 策略多样性 | 情绪控制 | 逻辑一致性。

- 输入：谈判历史（最近 10 轮）+ 场景背景
- 输出：4 维度 1-5 整数分 + weak_points + advice
- 兜底：LLM 不可用 / 解析失败 / Mock 模式时回退 _default_judge 中性分
"""

from __future__ import annotations

import logging
from typing import Any

from app.engine.llm import BaseLLM

logger = logging.getLogger(__name__)

DIMENSION_KEYS = ("naturalness", "strategy_diversity", "emotion_control", "logic_consistency")
DIMENSION_LABELS = {
    "naturalness": "话术自然度",
    "strategy_diversity": "策略多样性",
    "emotion_control": "情绪控制",
    "logic_consistency": "逻辑一致性",
}

JUDGE_PROMPT = """[复盘评估]
你是资深谈判教练，请对下面的谈判过程做主观评分。只输出 JSON，不要任何其他文字。

场景背景：{scenario_briefing}
评分维度（每题 1-5 分整数）：
- naturalness：用户话术是否自然、贴近真实谈判
- strategy_diversity：策略/战术使用是否多样
- emotion_control：情绪是否稳定、未被对手带节奏
- logic_consistency：论据与报价逻辑是否前后一致

谈判记录（最近 {rounds} 轮）：
{transcript}

输出格式：
{{
  "naturalness": 3,
  "strategy_diversity": 3,
  "emotion_control": 3,
  "logic_consistency": 3,
  "weak_points": ["问题1", "问题2"],
  "advice": "一条可执行的改进建议"
}}"""

MAX_ROUNDS = 10


def _clamp_score(value: Any, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(1.0, min(5.0, v))


def _transcript(history: list[dict]) -> str:
    lines = []
    for msg in history[-MAX_ROUNDS * 2 :]:
        role = msg.get("role", "user")
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        speaker = "用户" if role == "user" else "对手"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines) or "（无对话记录）"


async def default_judge(history: list[dict], scenario: dict) -> dict[str, Any]:
    """中性分兜底：4 维度 3.0 + 通用建议（LLM 不可用或解析失败时）。"""
    return {
        "naturalness": 3.0,
        "strategy_diversity": 3.0,
        "emotion_control": 3.0,
        "logic_consistency": 3.0,
        "weak_points": ["主动报价频率有待提升"],
        "advice": "建议在后续谈判中控制让步节奏，先让对方报价，再逐步小幅让价。",
    }


class LLMJudge:
    """LLM-as-Judge：由 BaseLLM 驱动的主观评分器。"""

    def __init__(self, llm: BaseLLM):
        self._llm = llm

    async def __call__(self, history: list[dict], scenario: dict) -> dict[str, Any]:
        try:
            prompt = JUDGE_PROMPT.format(
                scenario_briefing=scenario.get("briefing", "") or scenario.get("title", ""),
                rounds=min(len([m for m in history if m.get("content")]) // 2, MAX_ROUNDS),
                transcript=_transcript(history),
            )
            result = await self._llm.ainvoke_json(prompt, light=False)
            if not isinstance(result, dict):
                raise TypeError("judge 输出非 JSON 对象")
            return self._normalize(result)
        except Exception as exc:  # noqa: BLE001 评分失败不阻断报告生成
            logger.warning("LLM Judge 评估失败，回退默认分: %s", exc)
            return await default_judge(history, scenario)

    def _normalize(self, result: dict) -> dict[str, Any]:
        return {
            "naturalness": _clamp_score(result.get("naturalness"), 3.0),
            "strategy_diversity": _clamp_score(result.get("strategy_diversity"), 3.0),
            "emotion_control": _clamp_score(result.get("emotion_control"), 3.0),
            "logic_consistency": _clamp_score(result.get("logic_consistency"), 3.0),
            "weak_points": [
                str(w) for w in (result.get("weak_points") or [])[:3] if str(w).strip()
            ] or ["主动报价频率有待提升"],
            "advice": str(result.get("advice", "")).strip()
            or "建议在后续谈判中控制让步节奏，先让对方报价，再逐步小幅让价。",
        }


def build_judge(llm: BaseLLM | None = None) -> LLMJudge:
    """按需构建 Judge：默认复用引擎的 build_llm（配 key 走 OpenAI 兼容网关，否则 MockLLM）。"""
    from app.engine.engine import build_llm

    return LLMJudge(llm or build_llm())
