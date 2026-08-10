"""谈判会话 API 测试：创建会话、会话列表。"""

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
def auth_headers(client, session):
    client.post(
        "/api/auth/register",
        json={"username": "neg", "email": "neg@example.com", "password": "password123"},
    )
    login = client.post(
        "/api/auth/login",
        json={"account": "neg@example.com", "password": "password123"},
    ).json()
    return {"Authorization": f"Bearer {login['access_token']}"}


@pytest.fixture(autouse=True)
def free_quota(client, monkeypatch):
    """默认放行额度（避免真实 Redis 计数跨用例累积），配额专项测试单独覆盖。"""
    from app.api import sessions as sessions_api

    class AlwaysAllow:
        def check_and_increment(self, user_id, scenario_id):
            return True

    monkeypatch.setattr(sessions_api, "usage_counter", AlwaysAllow())


@pytest.fixture
def seeded_scenario(session):
    from app.services.scenario_seed import seed_scenarios

    seed_scenarios(session)
    session.commit()


def test_create_session_requires_auth(client):
    r = client.post("/api/sessions", json={"scenario_id": "it_procurement"})
    assert r.status_code == 401


def test_create_session_success(client, auth_headers, seeded_scenario):
    r = client.post(
        "/api/sessions",
        json={"scenario_id": "it_procurement"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["id"]
    assert body["scenario_id"] == "it_procurement"
    assert body["opening_line"]  # 开场白
    assert body["status"] == "active"


def test_create_session_unknown_scenario_returns_404(client, auth_headers):
    r = client.post(
        "/api/sessions",
        json={"scenario_id": "ghost_scenario"},
        headers=auth_headers,
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SCENARIO_NOT_FOUND"


def test_list_sessions_requires_auth(client):
    r = client.get("/api/sessions")
    assert r.status_code == 401


def test_list_sessions_returns_user_sessions(client, auth_headers, seeded_scenario):
    client.post(
        "/api/sessions",
        json={"scenario_id": "it_procurement"},
        headers=auth_headers,
    )
    r = client.get("/api/sessions", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["sessions"]) == 1
    assert r.json()["sessions"][0]["scenario_title"]


def test_list_sessions_isolated_between_users(client, session):
    client.post(
        "/api/auth/register",
        json={"username": "a_user", "email": "a@example.com", "password": "password123"},
    )
    client.post(
        "/api/auth/register",
        json={"username": "b_user", "email": "b@example.com", "password": "password123"},
    )
    token_a = client.post(
        "/api/auth/login",
        json={"account": "a@example.com", "password": "password123"},
    ).json()["access_token"]
    token_b = client.post(
        "/api/auth/login",
        json={"account": "b@example.com", "password": "password123"},
    ).json()["access_token"]

    from app.services.scenario_seed import seed_scenarios

    seed_scenarios(session)
    session.commit()

    client.post(
        "/api/sessions",
        json={"scenario_id": "it_procurement"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    r_b = client.get("/api/sessions", headers={"Authorization": f"Bearer {token_b}"})
    assert r_b.json()["sessions"] == []


def test_create_session_free_quota_exceeded(client, monkeypatch, seeded_scenario):
    from app.api import sessions as sessions_api

    calls = {"n": 0}

    class DenyAll:
        def check_and_increment(self, user_id, scenario_id):
            calls["n"] += 1
            return False

    monkeypatch.setattr(sessions_api, "usage_counter", DenyAll())

    client.post(
        "/api/auth/register",
        json={"username": "neg2", "email": "neg2@example.com", "password": "password123"},
    )
    tok = client.post(
        "/api/auth/login",
        json={"account": "neg2@example.com", "password": "password123"},
    ).json()["access_token"]

    r = client.post(
        "/api/sessions",
        json={"scenario_id": "it_procurement"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FREE_QUOTA_EXCEEDED"
    assert calls["n"] == 1


def test_create_session_pro_skips_quota(client, session, seeded_scenario, monkeypatch):
    from sqlalchemy import select

    from app.api import sessions as sessions_api
    from app.models import User

    called = {"n": 0}

    class FailCounter:
        def check_and_increment(self, user_id, scenario_id):
            called["n"] += 1
            return True

    monkeypatch.setattr(sessions_api, "usage_counter", FailCounter())

    client.post(
        "/api/auth/register",
        json={"username": "neg3", "email": "neg3@example.com", "password": "password123"},
    )
    u = session.scalar(select(User).where(User.email == "neg3@example.com"))
    u.role = "pro"
    session.commit()
    tok = client.post(
        "/api/auth/login",
        json={"account": "neg3@example.com", "password": "password123"},
    ).json()["access_token"]

    r = client.post(
        "/api/sessions",
        json={"scenario_id": "it_procurement"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201
    assert called["n"] == 0
