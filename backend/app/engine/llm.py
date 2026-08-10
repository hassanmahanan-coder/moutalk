"""LLM 客户端：GLM（OpenAI 兼容）可配置，无 key 时自动降级为规则引擎。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from contextvars import ContextVar

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.engine.extractor import first_price
from app.services.llm_rate_limit import LlmRateLimiter

logger = logging.getLogger(__name__)

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

# 限流上下文：WS 端点在调用引擎前设置当前用户 ID（PRD 9.6 令牌桶）
current_user_id: ContextVar[str | None] = ContextVar("moutalk_current_user_id", default=None)
_rate_limiter = LlmRateLimiter()


def set_rate_limit_user(user_id: str | None) -> None:
    """设置当前请求的用户 ID（LLM 令牌桶限流用）。"""
    current_user_id.set(user_id or "")


def _check_rate_limit() -> bool:
    """当前用户是否允许本次 LLM 调用；未登录/无 key 场景放行。"""
    uid = current_user_id.get()
    if not uid:
        return True
    return _rate_limiter.allow(uid)


def build_langfuse_handler():
    """LangFuse 观测 handler：LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY 齐全才启用（PRD 9.6）。

    用于挂载到 ChatOpenAI.callbacks，记录每次 LLM 调用的 token 消耗/延迟/模型。
    缺任一 key 返回 None（观测静默关闭），不会抛异常。
    """
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        try:
            from langfuse.langchain import CallbackHandler

            return CallbackHandler()
        except Exception as exc:  # noqa: BLE001 观测组件故障不阻断 LLM 调用
            logger.warning("LangFuse 初始化失败，观测关闭: %s", exc)
            return None
    return None


def rule_intent(text: str) -> dict:
    """无 LLM 时的规则兜底意图解析（关键词 + 数值提取）。"""
    intent_type = "other"
    if "报价" in text or "价格" in text or re.search(r"\d+(?:\.\d+)?\s*万元?", text):
        intent_type = "offer"
    elif any(w in text for w in ("可以接受", "可以谈", "适当降", "优惠", "折扣", "让步", "考虑")):
        intent_type = "concede"
    elif any(w in text for w in ("不行", "不接受", "拒绝", "不可能", "太贵", "没有余地", "免谈")):
        intent_type = "reject"
    elif any(w in text for w in ("怎么样", "如何", "行吗", "可否", "请问", "？", "?")):
        intent_type = "ask"
    return {
        "intent_type": intent_type,
        "price": first_price(text),
        "concessions": [w for w in ("可以接受", "可以谈", "适当降", "优惠", "折扣", "让步") if w in text],
        "emotion": (
            "eager" if any(w in text for w in ("尽快", "急需", "赶紧", "马上", "希望尽快", "着急"))
            else "angry" if any(w in text for w in ("过分", "欺人太甚", "愤怒", "失望", "无法接受", "凭什么"))
            else "neutral"
        ),
        "aggression_level": "high" if intent_type == "reject" else "low",
    }


class BaseLLM(ABC):
    """统一 LLM 接口，所有节点只依赖此抽象。"""

    configured: bool = False

    @abstractmethod
    async def ainvoke(self, prompt: str, *, light: bool = False) -> str: ...

    async def ainvoke_json(self, prompt: str, *, light: bool = False) -> dict:
        """调用模型并解析 JSON，容忍 markdown 代码块包裹。"""
        raw = await self.ainvoke(prompt, light=light)
        text = raw.strip()
        block = JSON_BLOCK_RE.search(text)
        if block:
            text = block.group(1).strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"LLM 输出不含 JSON: {raw[:200]}")
        return json.loads(text[start : end + 1])


class GLMClient(BaseLLM):
    """智谱 GLM（OpenAI 兼容协议）。"""

    configured: bool = True

    def __init__(self, settings: Settings):
        if not settings.llm_api_key:
            raise ValueError("LLM_API_KEY 未配置")
        callbacks = build_langfuse_handler()
        self._llm = ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.7,
            timeout=60,
            callbacks=[callbacks] if callbacks else None,
        )
        self._light = ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_light_model,
            temperature=0.3,
            timeout=60,
            callbacks=[callbacks] if callbacks else None,
        )

    async def ainvoke(self, prompt: str, *, light: bool = False) -> str:
        # PRD 9.6：单用户 LLM 令牌桶限流（超限返回占位话术，不阻断谈判流）
        if not _check_rate_limit():
            logger.warning("LLM 限流触发，返回降级话术")
            return "【系统繁忙】请稍候再试，当前请求过多。"
        llm = self._light if light else self._llm
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        return str(resp.content)


class MockLLM(BaseLLM):
    """无 key 时的确定性兜底：按关键词规则生成结构化意图/战术/话术。"""

    configured: bool = False

    OFFER_RE = re.compile(r"(?:报价|价格为|价钱|出价|报价为)?[:：]?\s*(\d+(?:\.\d+)?)\s*(万元|万|块|元)?")
    CONCESSION_WORDS = ("可以接受", "可以谈", "适当降", "优惠", "折扣", "让步", "考虑")
    REJECT_WORDS = ("不行", "不接受", "拒绝", "不可能", "太贵", "没有余地", "免谈")
    ASK_WORDS = ("怎么样", "如何", "行吗", "可否", "能", "请问", "？", "?")
    ANGER_WORDS = ("过分", "欺人太甚", "愤怒", "失望", "无法接受", "凭什么")
    EAGER_WORDS = ("尽快", "急需", "赶紧", "马上", "希望尽快", "着急")

    # 战术安全模板之外的通用沟通话术池（配合 策略 让回复随输入多样轮换）。
    GENERIC_UTTERANCES: tuple[str, ...] = (
        "您的方案我需要回去和团队确认一下。如果贵方能接受现款支付，我们可以在付款方式上做一些安排。",
        "我理解您的立场，但我们确实有自己的成本压力，希望我们能找到一个双方都能接受的方案。",
        "这个方向我们愿意再聊，不过需要放到整体方案里一起看，您还有其他诉求吗？",
        "您的意见我记下了。价格之外，我们更看重长期合作的稳定性。",
    )

    async def ainvoke(self, prompt: str, *, light: bool = False) -> str:
        if "[意图提取]" in prompt:
            return json.dumps(self._intent(prompt), ensure_ascii=False)
        if "[战术兜底]" in prompt:
            return json.dumps({"tactic": "silence_pressure", "reason": "mock 兜底"}, ensure_ascii=False)
        if "[复盘评估]" in prompt:
            return json.dumps(self._review(), ensure_ascii=False)
        return self._utterance(prompt)

    # ---------- 内部规则 ----------

    @classmethod
    def _extract_user_msg(cls, prompt: str) -> str:
        m = re.search(r"用户发言:[:：]?\s*(.+)$", prompt, re.MULTILINE)
        return m.group(1).strip() if m else prompt

    @classmethod
    def _intent(cls, prompt: str) -> dict:
        return rule_intent(cls._extract_user_msg(prompt))

    @classmethod
    def _review(cls) -> dict:
        return {
            "naturalness": 3,
            "strategy_diversity": 3,
            "emotion_control": 3,
            "logic_consistency": 3,
            "advice": "mock 评估：多尝试结构化报价，明确底线。",
        }

    @classmethod
    def _utterance_pool(cls, tactic: str) -> tuple[str, ...]:
        from app.engine.tactics import SAFE_TEMPLATES

        base = SAFE_TEMPLATES.get(tactic, SAFE_TEMPLATES.get("neutral", ()))
        return tuple(base) + cls.GENERIC_UTTERANCES

    @classmethod
    def _utterance(cls, prompt: str) -> str:
        tactic = re.search(r"当前战术[:：]?\s*([a-z_]+)", prompt)
        tactic = tactic.group(1) if tactic else "neutral"
        msg = cls._extract_user_msg(prompt)
        pool = cls._utterance_pool(tactic)
        # 确定性选择：同一(战术,用户消息)永远同句，不同输入/战术则轮换，避免固定文案。
        idx = int(hashlib.md5(f"{tactic}|{msg}".encode()).hexdigest(), 16) % len(pool)
        return pool[idx]
