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


def test_admin_tactic_stats_from_real_engine(client, admin_auth, session):
    """端到端：真实引擎跑一轮并持久化 → 战术命中非空（数据源为引擎 history）。"""
    import asyncio

    from sqlalchemy import select

    from app.engine.engine import NegotiationEngine
    from app.engine.llm import MockLLM
    from app.scenarios import load_scenario
    from app.services.session_store import create_session, save_round

    admin = session.scalar(select(User).where(User.email == "admin@example.com"))
    ns = create_session(session, admin.id, "it_procurement")
    session.commit()

    eng = NegotiationEngine(load_scenario("it_procurement"), llm=MockLLM())
    state = eng.initial_state(str(ns.id))
    state = asyncio.run(eng.run_round(state, "报价 200 万可以吗？"))
    save_round(session, ns.id, state)
    ns.status = "reported"  # 战术统计仅聚合已结束会话
    session.commit()

    r = client.get("/api/admin/tactic-stats", headers=admin_auth)
    data = r.json()
    assert data["total"] >= 1, "引擎轮次应产生战术命中"
    assert any(v > 0 for v in data["tactics"].values()), "tactics 不应全为零"


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


def test_admin_list_users(client, admin_auth, session):
    client.post(
        "/api/auth/register",
        json={"username": "alice_u", "email": "alice@example.com", "password": "password123"},
    )
    r = client.get("/api/admin/users", headers=admin_auth)
    assert r.status_code == 200
    users = r.json()["items"]
    assert any(u["email"] == "alice@example.com" for u in users)
    assert all("password_hash" not in u for u in users), "列表不得暴露密码哈希"


def test_admin_list_users_requires_admin(client, session, scenario):
    auth = _register(client, "normal2@example.com")
    assert client.get("/api/admin/users", headers=auth).status_code == 403


def test_admin_update_user_role(client, admin_auth, session):
    from app.models import UserRole

    client.post(
        "/api/auth/register",
        json={"username": "bob_u", "email": "bob@example.com", "password": "password123"},
    )
    target = session.scalar(select(User).where(User.email == "bob@example.com"))
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"role": "pro"},
        headers=admin_auth,
    )
    assert r.status_code == 200
    session.refresh(target)
    assert target.role == UserRole.PRO


def test_admin_update_user_role_writes_audit(client, admin_auth, session):
    from app.models import AdminAuditLog

    client.post(
        "/api/auth/register",
        json={"username": "cindy_u", "email": "cindy@example.com", "password": "password123"},
    )
    target = session.scalar(select(User).where(User.email == "cindy@example.com"))
    client.patch(
        f"/api/admin/users/{target.id}",
        json={"role": "pro"},
        headers=admin_auth,
    )
    log = session.scalar(
        select(AdminAuditLog).where(AdminAuditLog.action == "update_user_role")
    )
    assert log is not None
    assert log.target_id == str(target.id)


def test_admin_update_self_role_rejected(client, admin_auth, session):
    """管理员不可修改自己的角色（防自降/自升防护）。"""
    admin = session.scalar(select(User).where(User.email == "admin@example.com"))
    r = client.patch(
        f"/api/admin/users/{admin.id}",
        json={"role": "free"},
        headers=admin_auth,
    )
    assert r.status_code == 400


def test_admin_update_invalid_role_rejected(client, admin_auth, session):
    client.post(
        "/api/auth/register",
        json={"username": "dave_u", "email": "dave@example.com", "password": "password123"},
    )
    target = session.scalar(select(User).where(User.email == "dave@example.com"))
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"role": "superuser"},
        headers=admin_auth,
    )
    assert r.status_code == 422


def test_admin_update_unknown_user_404(client, admin_auth):
    r = client.patch(
        "/api/admin/users/00000000-0000-0000-0000-000000000000",
        json={"role": "pro"},
        headers=admin_auth,
    )
    assert r.status_code == 404


def test_admin_set_is_admin(client, admin_auth, session):
    """管理员可将他人设为管理员（防自改仍生效）。"""
    client.post(
        "/api/auth/register",
        json={"username": "newadm", "email": "newadm@example.com", "password": "password123"},
    )
    target = session.scalar(select(User).where(User.email == "newadm@example.com"))
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"is_admin": True},
        headers=admin_auth,
    )
    assert r.status_code == 200
    session.refresh(target)
    assert target.is_admin is True
    # 收回管理员
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"is_admin": False},
        headers=admin_auth,
    )
    session.refresh(target)
    assert target.is_admin is False


def test_admin_cannot_set_own_is_admin(client, admin_auth, session):
    """防自升：管理员不能修改自己的 is_admin。"""
    admin = session.scalar(select(User).where(User.email == "admin@example.com"))
    r = client.patch(
        f"/api/admin/users/{admin.id}",
        json={"is_admin": False},
        headers=admin_auth,
    )
    assert r.status_code == 400


# ---- 场景包管理（PRD 9.16 扩展：上下架/定价）----


def test_admin_list_scenarios(client, admin_auth, session, scenario):
    from app.services.scenario_seed import seed_scenarios

    seed_scenarios(session)
    session.commit()
    r = client.get("/api/admin/scenarios", headers=admin_auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 3
    assert all("config_json" not in i for i in items)


def test_admin_update_scenario_price(client, admin_auth, session, scenario):
    r = client.patch(
        "/api/admin/scenarios/it_procurement",
        json={"price": 129.0},
        headers=admin_auth,
    )
    assert r.status_code == 200
    assert float(r.json()["price"]) == 129.0


def test_admin_toggle_scenario_on_sale(client, admin_auth, session, scenario):
    r = client.patch(
        "/api/admin/scenarios/it_procurement",
        json={"on_sale": False},
        headers=admin_auth,
    )
    assert r.status_code == 200
    assert r.json()["on_sale"] is False
    # 用户端立即不可见
    assert client.get("/api/scenarios/it_procurement").status_code == 404


def test_admin_scenario_update_writes_audit(client, admin_auth, session, scenario):
    from app.models import AdminAuditLog

    client.patch(
        "/api/admin/scenarios/it_procurement",
        json={"on_sale": False},
        headers=admin_auth,
    )
    log = session.scalar(
        select(AdminAuditLog).where(AdminAuditLog.action == "update_scenario")
    )
    assert log is not None
    assert log.target_id == "it_procurement"


def test_admin_scenario_requires_admin(client, session, scenario):
    auth = _register(client, "normal3@example.com")
    assert client.get("/api/admin/scenarios", headers=auth).status_code == 403


def test_admin_access_writes_audit_log(client, admin_auth, session):
    """PRD 9.16 审计：管理操作必须落 admin_audit_log。"""
    from app.models import AdminAuditLog

    client.get("/api/admin/stats", headers=admin_auth)
    client.get("/api/admin/connections", headers=admin_auth)
    logs = session.scalars(
        select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
    ).all()
    actions = [l.action for l in logs]
    assert "view_stats" in actions
    assert "view_connections" in actions
