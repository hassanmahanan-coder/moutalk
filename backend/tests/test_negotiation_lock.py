"""谈判并发锁测试（PRD 9.13）：Redis 分布式锁防同一 session 并发 invoke。

- key: negotiation_lock:{session_id}，TTL 10s
- acquire 成功返回 True；已持有返回 False（→ API 层 429）
- 锁在 invoke 完成/异常时释放（release）
"""

import uuid

import pytest

from app.services.negotiation_lock import NegotiationLock


@pytest.fixture
def lock():
    return NegotiationLock(prefix="test_negotiation_lock:")


def test_acquire_and_release(lock):
    sid = str(uuid.uuid4())
    assert lock.acquire(sid) is True
    assert lock.acquire(sid) is False, "已持有锁时再次获取应失败"
    lock.release(sid)
    assert lock.acquire(sid) is True, "释放后可重新获取"


def test_lock_isolated_per_session(lock):
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    assert lock.acquire(a) is True
    assert lock.acquire(b) is True, "不同 session 锁互不影响"


def test_lock_auto_expires(lock):
    """TTL 10s 防止 LLM 卡死时永久锁死会话。"""
    sid = str(uuid.uuid4())
    assert lock.acquire(sid) is True
    assert lock.ttl(sid) > 0
    assert lock.ttl(sid) <= 10


def test_release_idempotent(lock):
    sid = str(uuid.uuid4())
    lock.release(sid)  # 未持有也释放不报错
    assert lock.acquire(sid) is True


def test_redis_down_degrades_gracefully(monkeypatch, lock):
    """Redis 不可用时放行（不阻断谈判主流程）。"""
    import redis

    def _boom(*args, **kwargs):
        raise redis.RedisError("redis down")

    monkeypatch.setattr(lock.client, "set", _boom)
    monkeypatch.setattr(lock.client, "delete", _boom)
    assert lock.acquire("sid") is True
    lock.release("sid")
