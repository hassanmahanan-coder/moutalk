"""管理后台 API 测试（PRD 9.16 / 故事 9）：KPI + 战术统计 + 连接数 + admin 鉴权。

契约：
- GET /api/admin/stats → {monthly_negotiations, paid_users, ...} 聚合值（不暴露明细）
- GET /api/admin/tactic-stats → 战术命中分布（聚合）
- GET /api/admin/connections → {online: N}
- 仅 is_admin=true 用户可访问（否则 403）
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


def _register(client, email, password="password123"):
    client.post(
        "/api/auth/register",
        json={"username": email.split("@")[0], "email": email, "password": password},
    )
    tok = client.post(
        "/api/auth/login", json={"account": email, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def admin_auth(client, session, scenario):
    client.post(
        "/api/auth/register",
        json={"username": "admin_user", "email": "admin@example.com", "password": "password123"},
    )
    u = session.scalar(select(User).where(User.email == "admin@example.com"))
    u.is_admin = True
    session.commit()
    tok = client.post(
        "/api/auth/login", json={"account": "admin@example.com", "password": "password123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _seed_data(session):
    from tests.test_reports_trends import _make_reported

    u = User(email="t1@example.com", password_hash="h")
    session.add(u)
    session.commit()
    _make_reported(session, u.id, 0.6, months_ago=0)


def test_admin_stats(client, admin_auth, session):
    _seed_data(session)
    r = client.get("/api/admin/stats", headers=admin_auth)
    assert r.status_code == 200
    data = r.json()
    assert "reports_count" in data
    assert data["reports_count"] >= 1
    assert "users_count" in data


def test_admin_tactic_stats(client, admin_auth):
    r = client.get("/api/admin/tactic-stats", headers=admin_auth)
    assert r.status_code == 200
    data = r.json()
    assert "tactics" in data
    assert isinstance(data["tactics"], dict)


def test_admin_connections(client, admin_auth):
    r = client.get("/api/admin/connections", headers=admin_auth)
    assert r.status_code == 200
    assert "online" in r.json()


def test_admin_requires_admin_role(client, session, scenario):
    auth = _register(client, "normal@example.com")
    for path in ["/api/admin/stats", "/api/admin/tactic-stats", "/api/admin/connections"]:
        r = client.get(path, headers=auth)
        assert r.status_code == 403, f"{path} 应 403"


def test_admin_requires_auth(client):
    assert client.get("/api/admin/stats").status_code == 401
