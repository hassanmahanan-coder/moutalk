"""WebSocket 谈判端点测试：连接鉴权、一轮对话、结束会话。"""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app


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
        json={"username": "ws_user", "email": "ws@example.com", "password": "password123"},
    )
    return client.post(
        "/api/auth/login",
        json={"account": "ws@example.com", "password": "password123"},
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


def test_ws_rejects_missing_token(client, session_id):
    with client.websocket_connect(f"/api/negotiation/{session_id}") as ws:
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert msg["code"] == "UNAUTHORIZED"


def test_ws_rejects_invalid_token(client, session_id):
    with client.websocket_connect(
        f"/api/negotiation/{session_id}?token=garbage-token"
    ) as ws:
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert msg["code"] == "INVALID_TOKEN"


def test_ws_sends_opening_line(client, token, session_id):
    with client.websocket_connect(
        f"/api/negotiation/{session_id}?token={token}"
    ) as ws:
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "opening"
        assert msg["text"]
        assert msg.get("llm_mode") == "mock"  # 测试环境无 key → MockLLM 降级


def test_ws_full_round_trip(client, token, session_id):
    with client.websocket_connect(
        f"/api/negotiation/{session_id}?token={token}"
    ) as ws:
        ws.receive_text()  # opening

        ws.send_text(json.dumps({"type": "user_msg", "text": "太贵了，180 万可以吗"}))

        # 流式 token（至少 1 个）
        chunks = []
        while True:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "token":
                chunks.append(msg["text"])
            elif msg["type"] == "meta":
                assert msg["tactic"] != ""
                assert "bottom_line" in msg
                break
        assert "".join(chunks) != ""


def test_ws_round_then_end(client, token, session_id):
    with client.websocket_connect(
        f"/api/negotiation/{session_id}?token={token}"
    ) as ws:
        ws.receive_text()  # opening
        ws.send_text(json.dumps({"type": "user_msg", "text": "你们能不能便宜点"}))
        while True:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "meta":
                break

        ws.send_text(json.dumps({"type": "end_negotiation"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "simple_result"
        assert "score" in msg or "summary" in msg


def test_ws_engine_error_notifies_user_and_keeps_connection(client, token, session_id, monkeypatch):
    """LLM/引擎异常时：用户收到错误提示，连接保持，可继续（不静默断连丢消息）。"""
    from app.engine import engine as engine_mod

    async def _boom(state, text, *, thread_id=None):
        raise RuntimeError("LLM 网关超时")

    monkeypatch.setattr(engine_mod.NegotiationEngine, "run_round", _boom)
    with client.websocket_connect(
        f"/api/negotiation/{session_id}?token={token}"
    ) as ws:
        ws.receive_text()  # opening
        ws.send_text(json.dumps({"type": "user_msg", "text": "你好"}))
        # 慢回复保活：先收到 thinking（受理确认），随后收到 error
        first = json.loads(ws.receive_text())
        if first["type"] == "thinking":
            first = json.loads(ws.receive_text())
        msg = first
        assert msg["type"] == "error"
        assert msg["code"] == "ENGINE_ERROR"
        # 连接未关闭：可继续发消息（ping 仍应答）
        ws.send_text(json.dumps({"type": "ping"}))
        pong = json.loads(ws.receive_text())
        assert pong["type"] == "pong"


def test_ws_persists_messages_to_db(client, token, session_id, session):
    with client.websocket_connect(
        f"/api/negotiation/{session_id}?token={token}"
    ) as ws:
        ws.receive_text()  # opening
        ws.send_text(json.dumps({"type": "user_msg", "text": "188 万，行不行"}))
        while True:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "meta":
                break

    from sqlalchemy import select

    from app.models import NegotiationSession

    ns = session.scalar(
        select(NegotiationSession).where(NegotiationSession.id == session_id)
    )
    assert ns is not None
    assert len(ns.messages_json) >= 2  # user + assistant


def test_ws_unknown_session_rejected(client, token):
    with client.websocket_connect(
        "/api/negotiation/00000000-0000-0000-0000-000000000000?token=" + token
    ) as ws:
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert msg["code"] == "SESSION_NOT_FOUND"


def test_ws_heartbeat_gets_pong(client, token, session_id):
    with client.websocket_connect(
        f"/api/negotiation/{session_id}?token={token}"
    ) as ws:
        ws.receive_text()  # opening
        ws.send_text(json.dumps({"type": "ping"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "pong"


def test_ws_reconnect_replays_history(client, token, session_id):
    with client.websocket_connect(
        f"/api/negotiation/{session_id}?token={token}"
    ) as ws:
        ws.receive_text()  # opening
        ws.send_text(json.dumps({"type": "user_msg", "text": "200 万，能不能行"}))
        while True:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "meta":
                break

    with client.websocket_connect(
        f"/api/negotiation/{session_id}?token={token}"
    ) as ws:
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "history", msg
        assert msg.get("llm_mode") == "mock"
        roles = [m["role"] for m in msg["messages"]]
        assert "user" in roles and "assistant" in roles
        assert any("200" in m["content"] for m in msg["messages"])
        assert isinstance(msg["offers"], list)
        assert msg["round"] >= 2
