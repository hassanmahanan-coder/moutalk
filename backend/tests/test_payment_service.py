"""支付服务测试：订单创建、Mock 回调、幂等、权限更新（PRD 7.5 / 9.12）。"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import (
    OrderStatus,
    OrderType,
    PaymentLog,
    UserRole,
    UserScenarioAccess,
)
from app.services.payment_service import (
    PRO_DAYS,
    create_order,
    process_paid_callback,
)


class TestCreateOrder:
    def test_create_subscribe_order(self, session, user):
        order = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
        assert order.type == OrderType.SUBSCRIBE
        assert order.amount == pytest.approx(199.0)
        assert order.status == OrderStatus.PENDING
        assert order.out_trade_no
        assert order.user_id == user.id

    def test_out_trade_no_unique(self, session, user):
        a = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
        b = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
        assert a.out_trade_no != b.out_trade_no


class TestProcessPaidCallback:
    def _subscribe_order(self, session, user, amount=199.0):
        return create_order(session, user.id, OrderType.SUBSCRIBE, None, amount)

    def test_callback_marks_paid_and_grants_pro(self, session, user):
        order = self._subscribe_order(session, user)
        before = datetime.now(UTC)
        result = process_paid_callback(
            session, order.out_trade_no, "alipay-tx-1", 199.0
        )
        assert result is True
        session.refresh(order)
        assert order.status == OrderStatus.PAID
        assert order.trade_no == "alipay-tx-1"
        session.refresh(user)
        assert user.role == UserRole.PRO
        assert user.expire_at is not None
        expire = user.expire_at if user.expire_at.tzinfo else user.expire_at.replace(tzinfo=UTC)
        assert before < expire <= before + timedelta(days=PRO_DAYS, seconds=1)
        # 幂等日志
        log = session.scalar(
            select(PaymentLog).where(PaymentLog.trade_no == "alipay-tx-1")
        )
        assert log is not None

    def test_callback_scenario_grants_access(self, session, user, scenario):
        order = create_order(
            session, user.id, OrderType.SCENARIO, scenario.id, 99.0
        )
        ok = process_paid_callback(
            session, order.out_trade_no, "alipay-tx-2", 99.0
        )
        assert ok is True
        access = session.scalar(
            select(UserScenarioAccess).where(
                UserScenarioAccess.user_id == user.id,
                UserScenarioAccess.scenario_id == scenario.id,
            )
        )
        assert access is not None

    def test_callback_amount_mismatch_rejected(self, session, user):
        order = self._subscribe_order(session, user)
        assert (
            process_paid_callback(
                session, order.out_trade_no, "alipay-tx-3", 199.0 + 0.01
            )
            is False
        )
        session.refresh(order)
        assert order.status == OrderStatus.PENDING
        session.refresh(user)
        assert user.role == UserRole.FREE

    def test_callback_unknown_order_rejected(self, session):
        assert (
            process_paid_callback(session, "no-such-order", "alipay-tx-4", 10.0)
            is False
        )

    def test_callback_idempotent_same_trade_no(self, session, user):
        order = self._subscribe_order(session, user)
        assert (
            process_paid_callback(
                session, order.out_trade_no, "alipay-tx-5", 199.0
            )
            is True
        )
        # 同一 trade_no 重复回调：直接 success 但不再变更
        assert (
            process_paid_callback(
                session, order.out_trade_no, "alipay-tx-5", 199.0
            )
            is True
        )
        count = len(session.scalars(select(PaymentLog)).all())
        assert count == 1

    def test_callback_idempotent_second_order_same_trade_no(self, session, user):
        o1 = self._subscribe_order(session, user)
        o2 = self._subscribe_order(session, user)
        assert (
            process_paid_callback(session, o1.out_trade_no, "alipay-tx-6", 199.0)
            is True
        )
        # 已消费过的 trade_no 不能再用于别的订单：返回成功（幂等），但订单保持 pending
        assert (
            process_paid_callback(session, o2.out_trade_no, "alipay-tx-6", 199.0)
            is True
        )
        session.refresh(o2)
        assert o2.status == OrderStatus.PENDING
