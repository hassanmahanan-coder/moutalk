"""谈判回放测试（PRD 9.17 / 故事 10）：从 sessions 重建时间轴。

契约：
- GET /api/sessions/{id}/replay → {rounds: [...], total_rounds, scenario_title}
- round = {round, user_text, reply, tactic, offer, bottom_line_status}
- 归属校验（他人会话 403）
- messages 奇数长度防御（末尾补空回复）
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_db
from app.main import app
from app.models import NegotiationSession, User
from tests.test_reports_api import _prices


@pytest.fixture
def client(session):
    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def user_id(client, session, scenario):
    client.post(
        "/api/auth/register",
        json={"username": "replay", "email": "replay@example.com", "password": "password123"},
    )
    u = session.scalar(select(User).where(User.email == "replay@example.com"))
    return u.id


@pytest.fixture
def auth(client, user_id):
    tok = client.post(
        "/api/auth/login",
        json={"account": "replay@example.com", "password": "password123"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _make_session(session, owner_id, messages, offers, scenario_id="it_procurement"):
    ns = NegotiationSession(
        user_id=owner_id,
        scenario_id=scenario_id,
        messages_json=messages,
        offers_json=offers,
        status="reported",
    )
    session.add(ns)
    session.commit()
    return ns


def test_replay_builds_rounds(client, auth, session, user_id):
    ns = _make_session(
        session,
        user_id,
        messages=[
            {"role": "user", "content": "报价太高"},
            {"role": "assistant", "content": "可以谈 210 万", "tactic": "divide_conquer"},
            {"role": "user", "content": "200 万"},
            {"role": "assistant", "content": "成交", "tactic": "concession_bait"},
        ],
        offers=_prices(235, 210, 200),
    )
    r = client.get(f"/api/sessions/{ns.id}/replay", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["total_rounds"] == 2
    r0 = data["rounds"][0]
    assert r0["user_text"] == "报价太高"
    assert r0["reply"] == "可以谈 210 万"
    assert r0["tactic"] == "divide_conquer"
    assert r0["offer"] == 235
    assert data["scenario_title"] == "IT 采购谈判"


def test_replay_odd_messages_defensive(client, auth, session, user_id):
    ns = _make_session(
        session,
        user_id,
        messages=[{"role": "user", "content": "只说了这一句"}],
        offers=_prices(235),
    )
    r = client.get(f"/api/sessions/{ns.id}/replay", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["total_rounds"] == 1
    assert data["rounds"][0]["reply"] == "", "奇数消息末尾补空回复"


def test_replay_other_user_forbidden(client, auth, session, user_id):
    other = User(email=f"o_{uuid.uuid4().hex[:8]}@x.com", password_hash="h")
    session.add(other)
    session.commit()
    ns = _make_session(session, other.id, [], [])
    r = client.get(f"/api/sessions/{ns.id}/replay", headers=auth)
    assert r.status_code == 403


def test_replay_not_found(client, auth):
    r = client.get("/api/sessions/00000000-0000-0000-0000-000000000000/replay", headers=auth)
    assert r.status_code == 404


def test_replay_tactic_from_real_engine(client, auth, session, user_id):
    """端到端：真实引擎一轮持久化 → 回放带战术与底线状态（非注入假数据）。"""
    import asyncio

    from app.engine.engine import NegotiationEngine
    from app.engine.llm import MockLLM
    from app.scenarios import load_scenario
    from app.services.session_store import create_session, save_round

    ns = create_session(session, user_id, "it_procurement")
    session.commit()

    eng = NegotiationEngine(load_scenario("it_procurement"), llm=MockLLM())
    state = eng.initial_state(str(ns.id))
    state = asyncio.run(eng.run_round(state, "报价 200 万可以吗？"))
    save_round(session, ns.id, state)
    session.commit()

    r = client.get(f"/api/sessions/{ns.id}/replay", headers=auth)
    assert r.status_code == 200
    r0 = r.json()["rounds"][0]
    assert r0["tactic"], "回放应含引擎实际使用的战术"
    assert r0["bottom_line_status"], "回放应含底线状态"
