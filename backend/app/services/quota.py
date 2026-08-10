"""免费额度服务：每月每场景 5 次（PRD 7.3 / 9.11）。

- Key 格式：`usage:{user_id}:{scenario_id}:{yyyymm}`，TTL 35 天（自然跨月失效）
- 用 Lua 原子 INCR + 比对，防并发超用（9.11）
- Pro 用户跳过检查（调用方按 role 判断）
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import redis as redis_lib
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)

FREE_LIMIT = 5
KEY_TTL_SECONDS = 35 * 24 * 3600  # 35 天，避免跨月累积

_LUA_CHECK_AND_INCR = """
local cur = redis.call('GET', KEYS[1])
if cur and tonumber(cur) >= tonumber(ARGV[1]) then return 0 end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
"""


def monthly_key(user_id: str, scenario_id: str, now: datetime | None = None) -> str:
    """月度计数 key：usage:{user_id}:{scenario_id}:{yyyymm}。"""
    now = now or datetime.now(UTC)
    return f"usage:{user_id}:{scenario_id}:{now.strftime('%Y%m')}"


def usage_key(prefix: str, user_id: str, scenario_id: str) -> str:
    return f"{prefix}{monthly_key(user_id, scenario_id)}"


class UsageCounter:
    """免费额度计数器（Redis Lua 原子操作，PRD 9.11）。"""

    def __init__(self, prefix: str = "usage:"):
        self.prefix = prefix
        self.client = redis_lib.from_url(get_settings().redis_url)

    def check_and_increment(self, user_id: str, scenario_id: str) -> bool:
        """原子检查并加 1；超过 FREE_LIMIT 返回 False（不计数）。"""
        key = usage_key(self.prefix, user_id, scenario_id)
        try:
            ok = bool(
                self.client.eval(
                    _LUA_CHECK_AND_INCR,
                    1,
                    key,
                    FREE_LIMIT,
                    KEY_TTL_SECONDS,
                )
            )
        except redis_lib.RedisError:
            logger.exception("额度计数 Redis 异常，放行")
            return True
        return ok

    def current_usage(self, user_id: str, scenario_id: str) -> int:
        key = usage_key(self.prefix, user_id, scenario_id)
        try:
            return int(self.client.get(key) or 0)
        except redis_lib.RedisError:
            logger.exception("额度查询 Redis 异常")
            return 0


def quota_summary(
    db: Session,
    user_id: uuid.UUID,
    role: str,
    limit: int = FREE_LIMIT,
) -> dict:
    """个人中心额度看板（PRD 7.7 / 故事 6）：各场景已用/剩余。

    - free 用户：limit=5/场景；pro/enterprise：limit=None（无限）
    - scenarios 来自 scenarios 表（内置 + 已购）
    """
    from sqlalchemy import select

    from app.models import Scenario

    counter = UsageCounter()
    rows = db.scalars(select(Scenario).order_by(Scenario.id)).all()
    is_unlimited = role in ("pro", "enterprise")
    scenarios = []
    for s in rows:
        used = 0 if is_unlimited else counter.current_usage(str(user_id), s.id)
        scenarios.append(
            {
                "scenario_id": s.id,
                "title": s.title,
                "used": used,
                "limit": None if is_unlimited else limit,
            }
        )
    return {
        "role": role,
        "limit": None if is_unlimited else limit,
        "scenarios": scenarios,
    }
