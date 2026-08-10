"""进步曲线 API 测试（PRD 9.18 / 故事 11）：按月聚合总分 + Pro/免费分级 + 缓存。

契约：
- GET /api/reports/trends?scenario_id=可选
- 返回 [{month, total, objective, subjective}] 按月升序
- 数据点 < 2 → {insufficient: true}
- 免费用户仅近 3 个月；Pro 完整
- 结果 Redis 缓存 1 小时（报告生成时失效）
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_db
from app.main import app
from app.models import NegotiationSession, Report, Scenario, ScenarioDomain, User
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
        json={"username": "trend", "email": "trend@example.com", "password": "password123"},
    )
    u = session.scalar(select(User).where(User.email == "trend@example.com"))
    return u.id


@pytest.fixture
def auth(client, user_id):
    tok = client.post(
        "/api/auth/login",
        json={"account": "trend@example.com", "password": "password123"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _make_reported(session, owner_id, total, months_ago=0):
    ns = NegotiationSession(
        user_id=owner_id,
        scenario_id="it_procurement",
        messages_json=[{"role": "user", "content": "hi"}],
        offers_json=_prices(235, 200),
        status="reported",
        ended_at=datetime.now(UTC) - timedelta(days=months_ago * 30),
    )
    session.add(ns)
    session.flush()
    rep = Report(
        session_id=ns.id,
        total_score=total,
        objective_json={"total": total, "dimensions": {"price_attainment": total}},
        subjective_json={"normalized": total, "dimensions": {"naturalness": 3}},
        concession_curve=[{"round": 1, "price": 235}],
        generated_at=datetime.now(UTC) - timedelta(days=months_ago * 30),
    )
    session.add(rep)
    session.commit()
    return rep


def test_trends_aggregates_by_month(client, auth, session, user_id):
    _make_reported(session, user_id, 0.5, months_ago=0)
    _make_reported(session, user_id, 0.7, months_ago=0)
    _make_reported(session, user_id, 0.6, months_ago=1)
    r = client.get("/api/reports/trends", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["insufficient"] is False
    assert len(data["points"]) == 2
    # 同月 2 条聚合为均值 (0.5+0.7)/2
    this_month = data["points"][-1]
    assert this_month["total"] == pytest.approx(0.6, abs=0.01)


def test_trends_insufficient_when_single_point(client, auth, session, user_id):
    _make_reported(session, user_id, 0.5, months_ago=0)
    r = client.get("/api/reports/trends", headers=auth)
    data = r.json()
    assert data["insufficient"] is True
    assert data["points"] == []


def test_trends_free_user_only_three_months(client, auth, session, user_id):
    # 免费用户：6 个月前的报告不可见
    _make_reported(session, user_id, 0.5, months_ago=0)
    _make_reported(session, user_id, 0.6, months_ago=1)
    _make_reported(session, user_id, 0.7, months_ago=5)  # 超过 3 个月
    r = client.get("/api/reports/trends", headers=auth)
    points = r.json()["points"]
    months = [p["month"] for p in points]
    assert len(months) == 2, f"免费用户应只见近 3 个月，实际 {months}"


def test_trends_pro_user_full_history(client, auth, session, user_id):
    u = session.get(User, user_id)
    u.role = "pro"
    session.commit()
    _make_reported(session, user_id, 0.5, months_ago=0)
    _make_reported(session, user_id, 0.7, months_ago=5)
    r = client.get("/api/reports/trends", headers=auth)
    assert len(r.json()["points"]) == 2, "Pro 用户应见完整历史"


def test_trends_scenario_filter(client, auth, session, user_id):
    _make_reported(session, user_id, 0.5, months_ago=0)
    s2 = Scenario(
        id="salary",
        domain=ScenarioDomain.SALARY,
        title="薪资谈判",
        config_json={"opening": {"price": 50}},
        is_free=True,
    )
    session.add(s2)
    session.commit()
    ns = NegotiationSession(
        user_id=user_id,
        scenario_id="salary",
        messages_json=[],
        offers_json=[],
        status="reported",
        ended_at=datetime.now(UTC),
    )
    session.add(ns)
    session.flush()
    rep = Report(
        session_id=ns.id,
        total_score=0.9,
        objective_json={"total": 0.9},
        subjective_json={"normalized": 0.9},
        concession_curve=[],
        generated_at=datetime.now(UTC),
    )
    session.add(rep)
    session.commit()
    # 再加一条 salary 报告（凑 2 个月数据点）
    ns2 = NegotiationSession(
        user_id=user_id,
        scenario_id="salary",
        messages_json=[],
        offers_json=[],
        status="reported",
        ended_at=datetime.now(UTC) - timedelta(days=35),
    )
    session.add(ns2)
    session.flush()
    rep2 = Report(
        session_id=ns2.id,
        total_score=0.8,
        objective_json={"total": 0.8},
        subjective_json={"normalized": 0.8},
        concession_curve=[],
        generated_at=datetime.now(UTC) - timedelta(days=35),
    )
    session.add(rep2)
    session.commit()
    r = client.get("/api/reports/trends?scenario_id=salary", headers=auth)
    points = r.json()["points"]
    assert len(points) == 2
    assert points[-1]["total"] == pytest.approx(0.9, abs=0.01)


def test_trends_unauthorized(client):
    r = client.get("/api/reports/trends")
    assert r.status_code == 401
