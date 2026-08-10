"""LLM 令牌桶限流（PRD 9.6）：单用户 LLM 调用 5 次/分钟。

- key: llm_rate:{user_id}:{yyyymmddhhmm}（每分钟窗口，Redis INCR + EXPIRE 60s）
- 超限返回 False（调用方拒绝本次 LLM 调用）
- Redis 不可用放行（不阻断谈判主流程）
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import redis as redis_lib

from app.core.config import get_settings

logger = logging.getLogger(__name__)

LLM_RATE_LIMIT = 5  # 次/分钟
WINDOW_SECONDS = 60


def rate_window_key(prefix: str, user_id: str, now: datetime | None = None) -> str:
    """分钟窗口 key：llm_rate:{user_id}:{yyyymmddhhmm}。"""
    now = now or datetime.now(UTC)
    return f"{prefix}{user_id}:{now.strftime('%Y%m%d%H%M')}"


class LlmRateLimiter:
    """Redis INCR 窗口计数器。"""

    def __init__(self, prefix: str = "llm_rate:"):
        self.prefix = prefix
        self.client = redis_lib.from_url(get_settings().redis_url)

    def allow(self, user_id: str) -> bool:
        """当前窗口内允许本次调用？超限 False。Redis 异常放行。"""
        key = rate_window_key(self.prefix, user_id)
        try:
            n = self.client.incr(key)
            if n == 1:
                self.client.expire(key, WINDOW_SECONDS)
            return int(n) <= LLM_RATE_LIMIT
        except redis_lib.RedisError:
            logger.warning("限流 Redis 异常，放行: %s", user_id)
            return True
