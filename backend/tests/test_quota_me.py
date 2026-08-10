"""个人中心额度 API 测试（PRD 7.7 / 故事 6）：/api/quota/me。

契约：
- GET /api/quota/me → {role, expire_at, scenarios: [{scenario_id, title, used, limit}]}
- free 用户：limit=5/场景，used 来自 Redis 计数
- pro 用户：limit=null（无限）+ 到期时间
- 未认证 401
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_db
from app.main import app
from app.models import User


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
    from app.services.scenario_seed import seed_scenarios

    seed_scenarios(session)
    session.commit()
    client.post(
        "/api/auth/register",
        json={"username": "me_user", "email": "me@example.com", "password": "password123"},
    )
    u = session.scalar(select(User).where(User.email == "me@example.com"))
    return u.id


@pytest.fixture
def auth(client, user_id):
    tok = client.post(
        "/api/auth/login",
        json={"account": "me@example.com", "password": "password123"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_quota_me_free_user(client, auth, session, user_id):
    r = client.get("/api/quota/me", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "free"
    assert data["limit"] == 5
    # 至少包含 3 个内置场景
    assert len(data["scenarios"]) >= 3
    for s in data["scenarios"]:
        assert "scenario_id" in s
        assert "used" in s
        assert s["limit"] == 5


def test_quota_me_tracks_usage(client, auth, session, user_id):
    from app.services.quota import UsageCounter

    UsageCounter(prefix="usage:").check_and_increment(str(user_id), "it_procurement")
    r = client.get("/api/quota/me", headers=auth)
    scenarios = {s["scenario_id"]: s for s in r.json()["scenarios"]}
    assert scenarios["it_procurement"]["used"] == 1


def test_quota_me_pro_user(client, auth, session, user_id):
    u = session.get(User, user_id)
    u.role = "pro"
    session.commit()
    r = client.get("/api/quota/me", headers=auth)
    data = r.json()
    assert data["role"] == "pro"
    assert data["limit"] is None, "Pro 无限次数"


def test_quota_me_unauthorized(client):
    assert client.get("/api/quota/me").status_code == 401
