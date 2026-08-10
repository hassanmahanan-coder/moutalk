"""断线缓冲队列（PRD 8.2 / 9.1）：断线期间完成的轮次缓存到 Redis，重连后回放。

- key 格式：`negotiation_buffer:{session_id}`（List）
- 协议：客户端重连发 {type:'resume'} → 服务端 drain 后回放 {type:'replay', messages:[...]}
- TTL 30 分钟：断线重连窗口内有效，逾期自动过期
- Redis 不可用时静默降级（不阻断谈判主流程）
"""

from __future__ import annotations

import logging
from typing import Any

import redis as redis_lib

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BUFFER_TTL_SECONDS = 30 * 60  # 30 分钟重连窗口


class WsBuffer:
    """谈判轮次断线缓冲（Redis List）。"""

    def __init__(self, prefix: str = "negotiation_buffer:"):
        self.prefix = prefix
        self.client = redis_lib.from_url(get_settings().redis_url)

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    def push(self, session_id: str, message: dict[str, Any]) -> None:
        """追加一条缓冲消息（断线期间完成的轮次）。"""
        try:
            key = self._key(session_id)
            self.client.rpush(key, __import__("json").dumps(message, ensure_ascii=False))
            self.client.expire(key, BUFFER_TTL_SECONDS)
        except redis_lib.RedisError:
            logger.warning("断线缓冲写入 Redis 异常，跳过: %s", session_id)

    def drain(self, session_id: str) -> list[dict[str, Any]]:
        """取出并清空该会话的全部缓冲消息（回放用）。"""
        try:
            key = self._key(session_id)
            raw = self.client.lrange(key, 0, -1) or []
            if raw:
                self.client.ltrim(key, len(raw), -1)  # 清空已读部分
            return [__import__("json").loads(r) for r in raw]
        except redis_lib.RedisError:
            logger.warning("断线缓冲读取 Redis 异常，返回空: %s", session_id)
            return []

    def ttl(self, session_id: str) -> int:
        try:
            return int(self.client.ttl(self._key(session_id)) or 0)
        except redis_lib.RedisError:
            return 0
