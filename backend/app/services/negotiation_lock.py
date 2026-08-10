"""谈判会话并发锁（PRD 9.13）：Redis 分布式锁防同一 session 并发 invoke。

- key: negotiation_lock:{session_id}，SET NX EX 10（原子获取 + TTL 10s 防死锁）
- 已持有锁时 acquire 返回 False → API 层返回 429 Processing previous message
- 锁在 invoke 完成/异常时由调用方 finally 释放
- Redis 不可用时放行（不阻断谈判主流程）
"""

from __future__ import annotations

import logging

import redis as redis_lib

from app.core.config import get_settings

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 10  # LLM 卡死时 10s 自动过期，防永久锁死


class NegotiationLock:
    """基于 Redis SET NX EX 的谈判会话锁。"""

    def __init__(self, prefix: str = "negotiation_lock:"):
        self.prefix = prefix
        self.client = redis_lib.from_url(get_settings().redis_url)

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    def acquire(self, session_id: str) -> bool:
        """原子获取锁：成功 True；已被持有 False。Redis 异常放行。"""
        try:
            ok = self.client.set(self._key(session_id), "1", nx=True, ex=LOCK_TTL_SECONDS)
            return bool(ok)
        except redis_lib.RedisError:
            logger.warning("谈判锁 Redis 异常，放行: %s", session_id)
            return True

    def release(self, session_id: str) -> None:
        """释放锁（幂等：未持有也安全）。Redis 异常忽略。"""
        try:
            self.client.delete(self._key(session_id))
        except redis_lib.RedisError:
            logger.warning("谈判锁释放 Redis 异常，忽略: %s", session_id)

    def ttl(self, session_id: str) -> int:
        try:
            return int(self.client.ttl(self._key(session_id)) or 0)
        except redis_lib.RedisError:
            return 0
