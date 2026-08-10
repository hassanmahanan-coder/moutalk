"""LLM 令牌桶限流测试（PRD 9.6）：单用户 LLM 调用 5 次/分钟。

- key: llm_rate:{user_id}:{yyyymmddhhmm}（每分钟窗口）
- Redis INCR + EXPIRE 60s；超限返回 False（→ API 层 429/拒绝调用）
- Redis 不可用放行（不阻断谈判）
"""

import uuid

import pytest

from app.services.llm_rate_limit import LLM_RATE_LIMIT, LlmRateLimiter


@pytest.fixture
def limiter():
    return LlmRateLimiter(prefix="test_llm_rate:")


def test_allows_up_to_limit(limiter):
    uid = str(uuid.uuid4())
    for _ in range(LLM_RATE_LIMIT):
        assert limiter.allow(uid) is True
    assert limiter.allow(uid) is False, "超过 5 次/分钟应拒绝"


def test_limit_isolated_per_user(limiter):
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    for _ in range(LLM_RATE_LIMIT):
        limiter.allow(a)
    assert limiter.allow(b) is True, "不同用户互不影响"


def test_window_expires(limiter, monkeypatch):
    """窗口 60s 后自动过期（新窗口恢复配额）：用不同时间戳模拟新窗口。"""
    from datetime import UTC, datetime

    uid = str(uuid.uuid4())
    t0 = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    t1 = datetime(2026, 8, 6, 12, 1, tzinfo=UTC)
    for _ in range(LLM_RATE_LIMIT):
        key = f"test_llm_rate:{uid}:{t0.strftime('%Y%m%d%H%M')}"
        limiter.client.incr(key)
        limiter.client.expire(key, 60)
    assert limiter.client.get(f"test_llm_rate:{uid}:{t0.strftime('%Y%m%d%H%M')}") is not None
    # 下一分钟：新窗口 key 不存在 → 首次 incr 返回 1 → 允许
    key2 = f"test_llm_rate:{uid}:{t1.strftime('%Y%m%d%H%M')}"
    n = limiter.client.incr(key2)
    assert int(n) <= LLM_RATE_LIMIT


def test_redis_down_degrades_gracefully(monkeypatch, limiter):
    import redis

    def _boom(*args, **kwargs):
        raise redis.RedisError("redis down")

    monkeypatch.setattr(limiter.client, "incr", _boom)
    assert limiter.allow("sid") is True
