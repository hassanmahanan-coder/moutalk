"""复盘报告 API 测试：列表 + 详情 + 数据隔离（PRD 8.4 / 9.9）。"""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_db
from app.main import app
from app.models import NegotiationSession, Report, User


def _prices(*values: float) -> list[dict]:
    return [{"reply": f"报价 {v} 万", "numbers": v} for v in values]


@pytest.fixture
def client(session):
    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def user_id(client, session):
    client.post(
        "/api/auth/register",
        json={"username": "rep", "email": "rep@example.com", "password": "password123"},
    )
    u = session.scalar(select(User).where(User.email == "rep@example.com"))
    return u.id


@pytest.fixture
def auth(client, user_id):
    tok = client.post(
        "/api/auth/login",
        json={"account": "rep@example.com", "password": "password123"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _make_report(session, owner_id, total=0.8):
    ns = NegotiationSession(
        user_id=owner_id,
        scenario_id="it_procurement",
        messages_json=[{"role": "user", "content": "hi"}],
        offers_json=_prices(235, 200),
    )
    session.add(ns)
    session.commit()
    rep = Report(
        session_id=ns.id,
        total_score=total,
        objective_json={"total": 0.8, "dimensions": {"price_attainment": 0.8}},
        subjective_json={"normalized": 0.5, "dimensions": {"naturalness": 3}},
        concession_curve=[{"round": 1, "price": 235}],
        weak_points=["让步过快"],
        advice="多使用时间压迫战术",
    )
    session.add(rep)
    session.commit()
    return rep


def _make_other_user(session, email="rival@example.com"):
    other = User(email=email, password_hash="hashed")
    session.add(other)
    session.commit()
    return other


def test_reports_requires_auth(client):
    assert client.get("/api/reports").status_code == 401
    assert client.get(f"/api/reports/{uuid.uuid4()}").status_code == 401


def test_list_reports_empty(client, auth, session):
    r = client.get("/api/reports", headers=auth)
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_list_reports_returns_items(client, auth, session, user_id, scenario):
    _make_report(session, user_id)
    r = client.get("/api/reports", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["total_score"] == 0.8
    assert items[0]["scenario_id"] == "it_procurement"


def test_list_reports_isolates_users(client, auth, session, user_id, scenario):
    _make_report(session, user_id)
    other = _make_other_user(session)
    _make_report(session, other.id)
    r = client.get("/api/reports", headers=auth)
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["session_id"] == str(
        session.scalars(select(Report)).all()[0].session_id
    )


def test_get_report_detail(client, auth, session, user_id, scenario):
    rep = _make_report(session, user_id)
    r = client.get(f"/api/reports/{rep.id}", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(rep.id)
    assert body["objective_json"]["dimensions"]["price_attainment"] == 0.8
    assert body["subjective_json"]["dimensions"]["naturalness"] == 3
    assert body["weak_points"] == ["让步过快"]
    assert body["advice"] == "多使用时间压迫战术"
    assert body["concession_curve"][0]["price"] == 235


def test_get_report_404_for_missing(client, auth):
    r = client.get(f"/api/reports/{uuid.uuid4()}", headers=auth)
    assert r.status_code == 404


def test_get_report_403_for_other_user(client, auth, session, scenario):
    other = _make_other_user(session)
    rep = _make_report(session, other.id)
    r = client.get(f"/api/reports/{rep.id}", headers=auth)
    assert r.status_code == 403


def test_pdf_download_requires_auth(client):
    assert client.get(f"/api/reports/{uuid.uuid4()}/pdf").status_code == 401


def test_pdf_download_404_when_not_exported(client, auth, session, user_id, scenario, tmp_path):
    """非 dev 环境（走 Celery 异步）首次请求触发导出但立即 404（未就绪）。"""
    from app.core.config import get_settings

    rep = _make_report(session, user_id)
    settings = get_settings()
    orig_env = settings.app_env
    settings.app_env = "prod"  # 非 dev：走 Celery 异步路径
    try:
        with patch("app.celery_app.export_pdf.delay", return_value=None), patch.object(
            get_settings(), "pdf_output_dir", str(tmp_path)
        ):
            r = client.get(f"/api/reports/{rep.id}/pdf", headers=auth)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "PDF_NOT_READY"
        assert not (tmp_path / f"report_{rep.id}.pdf").exists()
    finally:
        settings.app_env = orig_env


def test_pdf_download_dev_sync_exports(client, auth, session, user_id, scenario, tmp_path):
    """dev 环境首次请求即同步导出（本机无 Celery worker 的降级路径）。"""
    from app.core.config import get_settings

    rep = _make_report(session, user_id)
    settings = get_settings()
    orig_env = settings.app_env
    settings.app_env = "dev"
    try:
        with patch.object(get_settings(), "pdf_output_dir", str(tmp_path)):
            r = client.get(f"/api/reports/{rep.id}/pdf", headers=auth)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert (tmp_path / f"report_{rep.id}.pdf").exists()
        assert len(r.content) > 1000
    finally:
        settings.app_env = orig_env


def test_pdf_download_returns_file(client, auth, session, user_id, scenario, tmp_path):
    from unittest.mock import patch

    from app.core.config import get_settings
    from app.services.celery_tasks import export_report_pdf

    rep = _make_report(session, user_id)
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=session.get_bind(), autoflush=False)
    export_report_pdf(Session, rep.id, out_dir=str(tmp_path))
    session.expire_all()
    rep.pdf_url = f"/media/reports/report_{rep.id}.pdf"
    session.commit()

    with patch.object(get_settings(), "pdf_output_dir", str(tmp_path)):
        r = client.get(f"/api/reports/{rep.id}/pdf", headers=auth)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
