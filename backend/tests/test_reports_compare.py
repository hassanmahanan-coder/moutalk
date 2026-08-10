"""报告对比 API 测试（PRD 故事 4 / 阶段 2：历史报告对比 + 进步曲线）。

契约：
- GET /api/reports/compare?ids=a,b,c（2-5 份，逗号分隔）
- 数据隔离：只能对比自己的报告（他人报告 → 403）
- 返回按生成时间倒序的报告对比数据（总分/客观/主观/曲线/场景）
- ids 不足 2 份或超过 5 份 → 400
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_db
from app.main import app
from app.models import User
from tests.test_reports_api import _make_other_user, _make_report


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
        json={"username": "cmp", "email": "cmp@example.com", "password": "password123"},
    )
    u = session.scalar(select(User).where(User.email == "cmp@example.com"))
    return u.id


@pytest.fixture
def auth(client, user_id):
    tok = client.post(
        "/api/auth/login",
        json={"account": "cmp@example.com", "password": "password123"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_compare_two_reports(client, auth, session, user_id):
    r1 = _make_report(session, user_id, total=0.7)
    r2 = _make_report(session, user_id, total=0.9)
    r = client.get(f"/api/reports/compare?ids={r1.id},{r2.id}", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    scores = [x["total_score"] for x in data["reports"]]
    assert sorted(scores, reverse=True) == scores, "按总分降序"
    for item in data["reports"]:
        assert item["objective_json"]["total"] is not None
        assert "concession_curve" in item


def test_compare_requires_min_two(client, auth, session, user_id):
    r1 = _make_report(session, user_id)
    r = client.get(f"/api/reports/compare?ids={r1.id}", headers=auth)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_COMPARE_COUNT"


def test_compare_rejects_more_than_five(client, auth, session, user_id):
    ids = []
    for _ in range(6):
        ids.append(str(_make_report(session, user_id).id))
    r = client.get(f"/api/reports/compare?ids={','.join(ids)}", headers=auth)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_COMPARE_COUNT"


def test_compare_rejects_other_users_report(client, auth, session, user_id):
    mine = _make_report(session, user_id)
    other_user = _make_other_user(session, "rival_cmp@example.com")
    theirs = _make_report(session, other_user.id)
    r = client.get(f"/api/reports/compare?ids={mine.id},{theirs.id}", headers=auth)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_compare_rejects_missing_report(client, auth, session, user_id):
    mine = _make_report(session, user_id)
    r = client.get(f"/api/reports/compare?ids={mine.id},00000000-0000-0000-0000-000000000000", headers=auth)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "REPORT_NOT_FOUND"


def test_compare_invalid_uuid(client, auth):
    r = client.get("/api/reports/compare?ids=not-a-uuid,also-bad", headers=auth)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "REPORT_NOT_FOUND"


def test_compare_unauthorized(client):
    r = client.get("/api/reports/compare?ids=a,b")
    assert r.status_code == 401
