import pytest
from sqlalchemy import func

from app.models import (
    NegotiationSession,
    Order,
    OrderStatus,
    OrderType,
    PaymentLog,
    Report,
    Scenario,
    User,
)


def test_create_tables(test_engine):
    from sqlalchemy import inspect

    tables = set(inspect(test_engine).get_table_names())
    assert {
        "users",
        "scenarios",
        "user_scenario_access",
        "sessions",
        "reports",
        "orders",
        "payment_log",
    }.issubset(tables)


def test_user_roundtrip(session, user):
    from app.models import UserRole

    fetched = session.get(User, user.id)
    assert fetched is not None
    assert fetched.email == "alice@example.com"
    assert fetched.role == UserRole.FREE


def test_user_email_unique(session, user):
    from sqlalchemy.exc import IntegrityError

    dup = User(email="alice@example.com", password_hash="other")
    session.add(dup)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_scenario_roundtrip(session, scenario):
    from app.models import ScenarioDomain

    fetched = session.get(Scenario, scenario.id)
    assert fetched.domain == ScenarioDomain.IT_PROCUREMENT
    assert fetched.config_json["opening"]["price"] == 100
    assert fetched.is_free is True


def test_user_scenario_access_composite_pk(session, user, scenario):
    from app.models import UserScenarioAccess

    access = UserScenarioAccess(user_id=user.id, scenario_id=scenario.id)
    session.add(access)
    session.commit()

    again = UserScenarioAccess(user_id=user.id, scenario_id=scenario.id)
    session.add(again)
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_session_roundtrip_with_json(session, user, scenario):
    ns = NegotiationSession(user_id=user.id, scenario_id=scenario.id)
    ns.messages_json = [{"role": "user", "content": "hi"}]
    ns.offers_json = [{"round": 1, "price": 90}]
    session.add(ns)
    session.commit()

    fetched = session.get(NegotiationSession, ns.id)
    assert fetched.messages_json[0]["role"] == "user"
    assert fetched.offers_json[0]["price"] == 90
    assert fetched.status.name == "ACTIVE"


def test_report_unique_session(session, user, scenario):
    ns = NegotiationSession(user_id=user.id, scenario_id=scenario.id)
    session.add(ns)
    session.flush()

    session.add(Report(session_id=ns.id, total_score=72.5))
    session.add(Report(session_id=ns.id, total_score=80.0))
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_order_flow(session, user):
    order = Order(
        user_id=user.id,
        type=OrderType.SUBSCRIBE,
        amount=29.9,
        out_trade_no="MT202607010001",
    )
    session.add(order)
    session.commit()

    order.status = OrderStatus.PAID
    order.trade_no = "2026070100000001"
    session.commit()

    fetched = session.get(Order, order.id)
    assert fetched.status == OrderStatus.PAID
    assert fetched.trade_no == "2026070100000001"


def test_order_out_trade_no_unique(session, user):
    from sqlalchemy.exc import IntegrityError

    session.add(
        Order(user_id=user.id, type=OrderType.SUBSCRIBE, amount=10, out_trade_no="DUP")
    )
    session.add(
        Order(user_id=user.id, type=OrderType.SUBSCRIBE, amount=10, out_trade_no="DUP")
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_payment_log_unique_trade_no(session):
    session.add(PaymentLog(trade_no="T1"))
    session.commit()
    session.add(PaymentLog(trade_no="T1"))
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_cascade_delete_user_removes_sessions(session, user, scenario):
    ns = NegotiationSession(user_id=user.id, scenario_id=scenario.id)
    session.add(ns)
    session.commit()

    from sqlalchemy import delete, select

    ns_id = ns.id
    session.expunge(ns)
    session.execute(delete(User).where(User.id == user.id))
    session.commit()

    count = session.scalar(
        select(func.count()).select_from(NegotiationSession).where(
            NegotiationSession.id == ns_id
        )
    )
    assert count == 0
