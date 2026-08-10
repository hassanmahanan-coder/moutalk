"""支付主动对账测试：Celery Beat 定期扫描 PENDING 订单补登记（PRD 7.5 / 9.12）。

核心设计要求：
- 只扫描「超时仍 PENDING」的订单，已 PAID 不碰
- query_order 返回已支付 → 复用 process_paid_callback 补登（幂等，不重复授权）
- query_order 不可用 / 抛异常 → 降级跳过（不误授权），订单保持 PENDING
- 返回统计以便告警
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import (
    Order,
    OrderStatus,
    OrderType,
    PaymentLog,
    UserRole,
    UserScenarioAccess,
)
from app.services.payment_service import create_order, reconcile_pending_payments

TIMEOUT_MINUTES = 30


def _stale_order(session, user, scenario, user_id_override=None, amount=199.0):
    order = create_order(
        session, user_id_override or user.id, OrderType.SUBSCRIBE, None, amount
    )
    order.created_at = datetime.now(UTC) - timedelta(minutes=60)
    session.commit()
    return order


@pytest.fixture
def stale_order(session, user, scenario):
    return _stale_order(session, user, scenario)


class TestReconcilePendingPayments:
    def test_reconcile_marks_paid_when_alipay_says_success(
        self, session, user, stale_order
    ):
        def query_order(out_trade_no):
            return {"trade_no": "alipay-recon-1", "trade_status": "TRADE_SUCCESS"}

        stats = reconcile_pending_payments(
            session, query_order=query_order, timeout_minutes=TIMEOUT_MINUTES
        )
        assert stats["scanned"] == 1
        assert stats["reconciled"] == 1

        session.expire_all()
        order = session.get(Order, stale_order.id)
        assert order.status == OrderStatus.PAID
        assert order.trade_no == "alipay-recon-1"
        session.refresh(user)
        assert user.role == UserRole.PRO
        log = session.scalar(
            select(PaymentLog).where(PaymentLog.trade_no == "alipay-recon-1")
        )
        assert log is not None

    def test_reconcile_is_idempotent(self, session, user, stale_order):
        def query_order(out_trade_no):
            return {"trade_no": "alipay-recon-2", "trade_status": "TRADE_SUCCESS"}

        reconcile_pending_payments(
            session, query_order=query_order, timeout_minutes=TIMEOUT_MINUTES
        )
        reconcile_pending_payments(
            session, query_order=query_order, timeout_minutes=TIMEOUT_MINUTES
        )
        # 已 PAID 订单不再被扫描，payment_log 不重复
        logs = session.scalars(
            select(PaymentLog).where(PaymentLog.trade_no == "alipay-recon-2")
        ).all()
        assert len(logs) == 1

    def test_reconcile_scenario_grants_access(self, session, user, scenario):
        order = create_order(session, user.id, OrderType.SCENARIO, scenario.id, 99.0)
        order.created_at = datetime.now(UTC) - timedelta(minutes=60)
        session.commit()

        def query_order(out_trade_no):
            return {"trade_no": "alipay-recon-3", "trade_status": "TRADE_SUCCESS"}

        reconcile_pending_payments(
            session, query_order=query_order, timeout_minutes=TIMEOUT_MINUTES
        )
        access = session.scalar(
            select(UserScenarioAccess).where(
                UserScenarioAccess.user_id == user.id,
                UserScenarioAccess.scenario_id == scenario.id,
            )
        )
        assert access is not None

    def test_reconcile_skips_when_alipay_not_paid(self, session, stale_order):
        def query_order(out_trade_no):
            return {"trade_no": "alipay-recon-4", "trade_status": "WAIT_BUYER_PAY"}

        stats = reconcile_pending_payments(
            session, query_order=query_order, timeout_minutes=TIMEOUT_MINUTES
        )
        assert stats["reconciled"] == 0
        session.expire_all()
        assert session.get(Order, stale_order.id).status == OrderStatus.PENDING

    def test_reconcile_degrades_when_query_unavailable(self, session, user, stale_order):
        """query_order 未传入（Mock 环境无真实查询能力）→ 降级跳过，不误授权。"""
        stats = reconcile_pending_payments(
            session, query_order=None, timeout_minutes=TIMEOUT_MINUTES
        )
        assert stats["skipped"] == 1
        session.expire_all()
        assert session.get(Order, stale_order.id).status == OrderStatus.PENDING
        session.refresh(user)
        assert user.role == UserRole.FREE

    def test_reconcile_ignores_query_errors(self, session, stale_order):
        def query_order(out_trade_no):
            raise RuntimeError("alipay query boom")

        stats = reconcile_pending_payments(
            session, query_order=query_order, timeout_minutes=TIMEOUT_MINUTES
        )
        assert stats["skipped"] == 1
        session.expire_all()
        assert session.get(Order, stale_order.id).status == OrderStatus.PENDING

    def test_reconcile_only_scans_stale_orders(self, session, user, scenario):
        fresh = _stale_order(session, user, scenario, user_id_override=user.id)
        fresh.created_at = datetime.now(UTC) - timedelta(minutes=5)
        session.commit()

        def query_order(out_trade_no):
            return {"trade_no": "alipay-recon-5", "trade_status": "TRADE_SUCCESS"}

        stats = reconcile_pending_payments(
            session, query_order=query_order, timeout_minutes=TIMEOUT_MINUTES
        )
        assert stats["scanned"] == 0  # 未超时不扫描
        session.expire_all()
        assert session.get(Order, fresh.id).status == OrderStatus.PENDING

    def test_reconcile_amount_mismatch_from_alipay_ignored(
        self, session, user, stale_order
    ):
        """支付宝返回金额与本地订单不符 → 拒绝对账（防御篡改/接错单）。"""
        def query_order(out_trade_no):
            return {
                "trade_no": "alipay-recon-6",
                "trade_status": "TRADE_SUCCESS",
                "total_amount": "99999.00",
            }

        stats = reconcile_pending_payments(
            session, query_order=query_order, timeout_minutes=TIMEOUT_MINUTES
        )
        assert stats["skipped"] == 1
        session.expire_all()
        assert session.get(Order, stale_order.id).status == OrderStatus.PENDING