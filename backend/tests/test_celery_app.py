"""Celery 异步任务测试：实例配置、报告生成核心（PRD 8.4）、eager 模式任务注册。"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models import NegotiationSession, Report, SessionStatus
from app.services.celery_tasks import run_full_report


@pytest.fixture
def ns(session, user):
    from app.models import NegotiationSession, SessionStatus
    from app.services.scenario_seed import seed_scenarios

    seed_scenarios(session)
    session.commit()
    ns = NegotiationSession(
        id=uuid.uuid4(),
        user_id=user.id,
        scenario_id="it_procurement",
        status=SessionStatus.ACTIVE,
        messages_json=[
            {"role": "user", "content": "太贵了，180 万可以吗"},
            {"role": "assistant", "content": "我们最多让到 195 万。"},
        ],
        offers_json=[{"round": 1, "numbers": 200}, {"round": 2, "numbers": 195}],
    )
    session.add(ns)
    session.commit()
    return ns


class TestCeleryAppConfig:
    def test_app_has_tasks_registered(self):
        from app.celery_app import app as celery_app

        assert "generate_full_report" in celery_app.tasks
        assert "export_pdf" in celery_app.tasks
        assert "reconcile_pending_payments" in celery_app.tasks

    def test_beat_schedule_has_reconcile(self):
        from app.celery_app import app as celery_app

        schedule = celery_app.conf.beat_schedule
        assert "reconcile-pending-payments" in schedule
        assert schedule["reconcile-pending-payments"]["task"] == "reconcile_pending_payments"

    def test_reconcile_task_degrades_in_mock(self, session, user):
        """Mock 环境（无真实查单）对账 task 应可执行且不改订单。"""
        from datetime import UTC, datetime, timedelta
        from unittest.mock import patch

        from sqlalchemy.orm import sessionmaker

        from app.models import Order, OrderStatus, OrderType
        from app.services.payment_service import create_order

        Session = sessionmaker(bind=session.get_bind(), autoflush=False)
        order = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
        order.created_at = datetime.now(UTC) - timedelta(hours=1)
        session.commit()

        with patch("app.celery_app.SessionLocal", new=Session):
            from app.celery_app import reconcile_pending_payments_task

            stats = reconcile_pending_payments_task.run(timeout_minutes=30)

        session.expire_all()
        order = session.get(Order, order.id)
        assert order.status == OrderStatus.PENDING
        assert stats == {"scanned": 1, "reconciled": 0, "skipped": 1}

    def test_broker_url_from_settings(self):
        from app.celery_app import app as celery_app

        assert celery_app.conf.broker_url == "redis://localhost:6379/1"


class TestRunFullReport:
    async def test_generates_and_persists_report(self, ns, session):
        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=session.get_bind(), autoflush=False)

        report = await run_full_report(Session, ns.id)

        assert isinstance(report, Report)
        assert report.session_id == ns.id
        assert report.total_score is not None
        assert report.objective_json is not None
        assert report.subjective_json is not None
        assert report.concession_curve is not None
        assert "price_attainment" in report.objective_json["dimensions"]

    async def test_persists_report_in_db(self, ns, session):
        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=session.get_bind(), autoflush=False)

        await run_full_report(Session, ns.id)

        session.expire_all()
        ns_row = session.get(NegotiationSession, ns.id)
        assert ns_row is not None
        assert ns_row.status == SessionStatus.REPORTED
        assert session.scalar(
            __import__("sqlalchemy").select(Report).where(Report.session_id == ns.id)
        ) is not None

    async def test_idempotent_no_duplicate(self, ns, session):
        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=session.get_bind(), autoflush=False)

        await run_full_report(Session, ns.id)
        await run_full_report(Session, ns.id)

        from sqlalchemy import select

        rows = session.scalars(select(Report).where(Report.session_id == ns.id)).all()
        assert len(rows) == 1

    async def test_raises_for_missing_session(self, session):
        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=session.get_bind(), autoflush=False)

        with pytest.raises(ValueError):
            await run_full_report(Session, uuid.uuid4())

    async def test_judge_failure_still_persists(self, ns, session):
        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=session.get_bind(), autoflush=False)

        async def failing_judge(history, scenario):
            raise RuntimeError("judge boom")

        report = await run_full_report(Session, ns.id, judge=failing_judge)

        assert report.subjective_json["dimensions"] == {}
        assert float(report.total_score) == round(0.6 * report.objective_json["total"], 2)


class TestGenerateFullReportTask:
    def test_task_runs_eagerly(self, ns, session):
        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=session.get_bind(), autoflush=False)
        with patch(
            "app.core.db.SessionLocal", new=Session
        ), patch("app.celery_app.run_full_report", new=AsyncMock(return_value="OK")) as m:
            from app.celery_app import generate_full_report

            generate_full_report.apply(args=[str(ns.id)])
            m.assert_called_once()
