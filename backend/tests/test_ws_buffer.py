"""断线缓冲队列测试（PRD 8.2 / 9.1）：断线期间后端完成的轮次缓存到 Redis，重连回放。

协议契约（WS）：
- 客户端心跳 {type:'ping'}，服务端 60s 无心跳判定断线（negotiation.py 实现）
- 客户端重连后发 {type:'resume'}，服务端回放 {type:'replay', messages:[...]}
- 缓冲 key：`negotiation_buffer:{session_id}`（List，TTL 30min）
"""

import uuid

import pytest

from app.services.ws_buffer import WsBuffer


@pytest.fixture
def buffer():
    return WsBuffer(prefix="test_ws_buffer:")


def test_push_and_drain_roundtrip(buffer):
    sid = str(uuid.uuid4())
    msg = {"role": "assistant", "reply": "450 万包含全部服务", "meta": {"tactic": "neutral"}}
    buffer.push(sid, msg)
    drained = buffer.drain(sid)
    assert drained == [msg]
    assert buffer.drain(sid) == [], "drain 后缓冲应清空"


def test_push_multiple_preserves_order(buffer):
    sid = str(uuid.uuid4())
    buffer.push(sid, {"role": "user", "reply": "太贵了"})
    buffer.push(sid, {"role": "assistant", "reply": "可以谈"})
    drained = buffer.drain(sid)
    assert [m["reply"] for m in drained] == ["太贵了", "可以谈"]


def test_drain_empty_returns_empty(buffer):
    sid = str(uuid.uuid4())
    assert buffer.drain(sid) == []


def test_sessions_isolated(buffer):
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    buffer.push(a, {"reply": "A"})
    buffer.push(b, {"reply": "B"})
    assert [m["reply"] for m in buffer.drain(a)] == ["A"]
    assert [m["reply"] for m in buffer.drain(b)] == ["B"]


def test_ttl_configured(buffer):
    sid = str(uuid.uuid4())
    buffer.push(sid, {"reply": "x"})
    assert buffer.ttl(sid) > 0, "缓冲应带 TTL 自动过期"


def test_redis_down_degrades_gracefully(monkeypatch, buffer):
    """Redis 不可用时 push/drain 不抛异常（静默降级，不阻断谈判）。"""

    def _boom(*args, **kwargs):
        import redis

        raise redis.RedisError("redis down")

    monkeypatch.setattr(buffer.client, "rpush", _boom)
    monkeypatch.setattr(buffer.client, "lrange", _boom)
    monkeypatch.setattr(buffer.client, "ltrim", _boom)
    monkeypatch.setattr(buffer.client, "expire", _boom)
    buffer.push("sid", {"reply": "x"})
    assert buffer.drain("sid") == []
