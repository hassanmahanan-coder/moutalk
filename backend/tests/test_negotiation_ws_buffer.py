"""断线缓冲队列集成测试（PRD 8.2 / 9.1）：轮次写入缓冲、ack 消费、resume 回放。

协议（补充 negotiation.py 契约）：
- 客户端 → 服务端：{type:'ack'} 确认已收到该轮 meta（清空缓冲）
- 客户端 → 服务端：{type:'resume'} 重连后请求回放断线期间缓冲的轮次
- 服务端 → 客户端：{type:'replay', messages:[{user_text, reply, meta}, ...]}
"""

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.services.ws_buffer import WsBuffer


@pytest.fixture
def client(session):
    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def token(client):
    client.post(
        "/api/auth/register",
        json={"username": "wsb", "email": "wsb@example.com", "password": "password123"},
    )
    return client.post(
        "/api/auth/login",
        json={"account": "wsb@example.com", "password": "password123"},
    ).json()["access_token"]


@pytest.fixture
def session_id(client, token, session):
    from app.services.scenario_seed import seed_scenarios

    seed_scenarios(session)
    session.commit()
    r = client.post(
        "/api/sessions",
        json={"scenario_id": "it_procurement"},
        headers={"Authorization": f"Bearer {token}"},
    )
    return r.json()["id"]


@pytest.fixture
def buffer(monkeypatch):
    """WS 端点内的 WsBuffer() 使用独立前缀（隔离测试数据）。"""
    from app.api import negotiation as neg_module

    b = WsBuffer(prefix="test_ws_buffer:")
    monkeypatch.setattr(neg_module, "WsBuffer", lambda: b)
    return b


def test_round_pushed_and_acked_clears_buffer(client, token, session_id, buffer):
    with client.websocket_connect(f"/api/negotiation/{session_id}?token={token}") as ws:
        ws.receive_json()  # opening
        ws.send_json({"type": "user_msg", "text": "235 万太高了，200 万"})
        seen_meta = False
        while not seen_meta:
            seen_meta = ws.receive_json()["type"] == "meta"
        assert buffer.drain(session_id), "未 ack 前轮次应在缓冲中"
        ws.send_json({"type": "ack"})
        assert buffer.drain(session_id) == [], "ack 后缓冲应清空"


def test_resume_replays_buffered_round(client, token, session_id, buffer):
    """断线期间缓冲的轮次，重连 resume 后以 replay 回放。"""
    buffer.push(
        session_id,
        {
            "user_text": "太贵了",
            "reply": "可以谈，450 万包含全部服务",
            "meta": {"tactic": "neutral"},
        },
    )
    with client.websocket_connect(f"/api/negotiation/{session_id}?token={token}") as ws:
        ws.receive_json()  # opening（无历史时）
        ws.send_json({"type": "resume"})
        msg = ws.receive_json()
        assert msg["type"] == "replay"
        assert len(msg["messages"]) == 1
        assert msg["messages"][0]["reply"] == "可以谈，450 万包含全部服务"
        assert buffer.drain(session_id) == [], "回放后缓冲应清空"


def test_resume_no_buffer_returns_empty_replay(client, token, session_id, buffer):
    with client.websocket_connect(f"/api/negotiation/{session_id}?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "resume"})
        msg = ws.receive_json()
        assert msg["type"] == "replay"
        assert msg["messages"] == []


def test_concurrent_msg_rejected_while_lock_held(client, token, session_id, buffer, monkeypatch):
    """PRD 9.13：锁被持有（上一条处理中）时新消息返回 429 PROCESSING_PREVIOUS_MESSAGE。"""
    from app.api import negotiation as neg_module

    held = {"locked": False}

    def fake_acquire(self, sid):
        if held["locked"]:
            return False
        held["locked"] = True
        return True

    def fake_release(self, sid):
        held["locked"] = False

    monkeypatch.setattr(neg_module.NegotiationLock, "acquire", fake_acquire)
    monkeypatch.setattr(neg_module.NegotiationLock, "release", fake_release)
    with client.websocket_connect(f"/api/negotiation/{session_id}?token={token}") as ws:
        ws.receive_json()
        # 第一次：锁空闲，正常处理（MockLLM 快）
        ws.send_json({"type": "user_msg", "text": "报价太高了"})
        seen_meta = False
        while not seen_meta:
            seen_meta = ws.receive_json()["type"] == "meta"
        # 模拟锁仍被持有：第二次消息应被拒
        held["locked"] = True
        ws.send_json({"type": "user_msg", "text": "再降一点"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "PROCESSING_PREVIOUS_MESSAGE"
