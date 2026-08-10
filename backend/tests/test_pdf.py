"""PDF 导出任务测试：reportlab PDF 生成、让步曲线 PNG、pdf_url 写回（PRD 9.10）。"""

import os
import uuid

import pytest

from app.models import NegotiationSession, Report, SessionStatus
from app.services.celery_tasks import export_report_pdf


@pytest.fixture
def rep(session, user):
    from app.services.scenario_seed import seed_scenarios

    seed_scenarios(session)
    session.commit()
    ns = NegotiationSession(
        id=uuid.uuid4(),
        user_id=user.id,
        scenario_id="it_procurement",
        status=SessionStatus.REPORTED,
        messages_json=[],
        offers_json=[{"round": 1, "numbers": 200}, {"round": 2, "numbers": 195}],
    )
    session.add(ns)
    session.commit()
    r = Report(
        session_id=ns.id,
        total_score=0.72,
        objective_json={
            "dimensions": {
                "price_attainment": 0.8,
                "concession_margin": 0.5,
                "bottom_line_hold": 1.0,
                "time_efficiency": 0.9,
            },
            "total": 0.83,
        },
        subjective_json={
            "dimensions": {"naturalness": 4.0, "strategy_diversity": 3.5},
            "normalized": 0.6,
            "weak_points": ["报价过快"],
            "advice": "慢点让步",
        },
        concession_curve=[
            {"round": 1, "price": 200, "label": "总价"},
            {"round": 2, "price": 195, "label": "总价"},
        ],
        weak_points=["报价过快"],
        advice="慢点让步",
    )
    session.add(r)
    session.commit()
    return r


def test_export_report_pdf_creates_file(rep, session, tmp_path):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=session.get_bind(), autoflush=False)

    pdf_path = export_report_pdf(Session, rep.id, out_dir=str(tmp_path))

    assert pdf_path is not None
    assert pdf_path.endswith(".pdf")
    assert os.path.exists(pdf_path)
    with open(pdf_path, "rb") as f:
        assert f.read(4) == b"%PDF"


def test_export_report_pdf_updates_pdf_url(rep, session, tmp_path):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=session.get_bind(), autoflush=False)

    export_report_pdf(Session, rep.id, out_dir=str(tmp_path))

    session.expire_all()
    r = session.get(Report, rep.id)
    assert r.pdf_url is not None
    assert r.pdf_url.endswith(".pdf")


def test_export_report_pdf_missing_report_raises(session, tmp_path):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=session.get_bind(), autoflush=False)

    with pytest.raises(ValueError):
        export_report_pdf(Session, uuid.uuid4(), out_dir=str(tmp_path))


def test_pdf_content_contains_score_text(rep, session, tmp_path):
    """PDF 内容应含总分卡（reportlab 文本层可提取）。"""
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=session.get_bind(), autoflush=False)

    pdf_path = export_report_pdf(Session, rep.id, out_dir=str(tmp_path))

    with open(pdf_path, "rb") as f:
        raw = f.read()
    # reportlab 会把文本写入 PDF 流；用简单文本提取验证含 score
    text = raw.decode("latin-1", errors="ignore")
    assert "0.72" in text or "72" in text


def test_export_report_pdf_empty_curve(rep, session, tmp_path):
    """让步曲线为空（无 offers）时仍应生成 PDF。"""
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=session.get_bind(), autoflush=False)
    rep.concession_curve = []
    session.commit()

    pdf_path = export_report_pdf(Session, rep.id, out_dir=str(tmp_path))
    assert pdf_path is not None
    assert os.path.exists(pdf_path)
