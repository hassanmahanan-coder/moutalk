"""支付 API 测试：创建订单 + Mock 回调（PRD 7.5 / 9.12）。"""

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models import OrderStatus, OrderType, UserRole, UserScenarioAccess
from app.services.payment_service import create_order


@pytest.fixture
def client(session):
    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    client.post(
        "/api/auth/register",
        json={"username": "pay", "email": "pay@example.com", "password": "password123"},
    )
    tok = client.post(
        "/api/auth/login",
        json={"account": "pay@example.com", "password": "password123"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def seeded_scenario(session):
    from app.services.scenario_seed import seed_scenarios

    seed_scenarios(session)
    session.commit()


def test_create_order_requires_auth(client):
    assert (
        client.post("/api/payment/orders", json={"type": "subscribe"}).status_code
        == 401
    )


def test_create_subscribe_order(client, auth):
    r = client.post("/api/payment/orders", json={"type": "subscribe"}, headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert body["out_trade_no"]
    assert body["amount"] == 199.0
    assert body["status"] == "pending"
    assert body["pay_url"].startswith("https://")


def test_create_scenario_order_requires_target(client, auth, session, scenario):
    r = client.post(
        "/api/payment/orders",
        json={"type": "scenario"},
        headers=auth,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "TARGET_REQUIRED"


def test_create_scenario_order_invalid_target(client, auth, session):
    r = client.post(
        "/api/payment/orders",
        json={"type": "scenario", "target_id": "ghost"},
        headers=auth,
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SCENARIO_NOT_FOUND"


def test_create_scenario_order(client, auth, session, seeded_scenario):
    from sqlalchemy import select

    from app.models import Scenario

    sc = session.scalar(select(Scenario).where(Scenario.id == "it_procurement"))
    sc.price = 99.0
    session.commit()

    r = client.post(
        "/api/payment/orders",
        json={"type": "scenario", "target_id": "it_procurement"},
        headers=auth,
    )
    assert r.status_code == 201
    assert r.json()["amount"] == 99.0


def test_create_order_503_when_payment_unconfigured(client, auth, monkeypatch):
    """支付宝密钥未配置 → build_pay_url 返回 None → API 503（前端提示暂不可用）。"""
    monkeypatch.setattr("app.api.payment.build_pay_url", lambda *a, **kw: None)
    r = client.post("/api/payment/orders", json={"type": "subscribe"}, headers=auth)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "PAYMENT_NOT_CONFIGURED"


def test_notify_marks_order_paid(client, session, user):
    order = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
    session.commit()
    r = client.post(
        "/api/payment/notify",
        data={
            "out_trade_no": order.out_trade_no,
            "trade_no": "alipay-api-1",
            "amount": "199.00",
        },
    )
    assert r.status_code == 200
    assert r.text == "success"
    session.refresh(order)
    assert order.status == OrderStatus.PAID


def test_notify_amount_mismatch_returns_fail(client, session, user):
    order = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
    session.commit()
    r = client.post(
        "/api/payment/notify",
        data={
            "out_trade_no": order.out_trade_no,
            "trade_no": "alipay-api-2",
            "amount": "1.00",
        },
    )
    assert r.text == "fail"
    session.refresh(order)
    assert order.status == OrderStatus.PENDING


def test_notify_unknown_order_returns_fail(client):
    r = client.post(
        "/api/payment/notify",
        data={"out_trade_no": "NOPE", "trade_no": "alipay-api-3", "amount": "1.00"},
    )
    assert r.text == "fail"


def test_notify_rejects_when_signature_configured(client, session, user, monkeypatch):
    """配置公钥后，无签名回调必须被拒（验签防伪，PRD 9.12）。"""
    from app.services import alipay_verify

    monkeypatch.setattr(alipay_verify, "_get_public_key", lambda: "fake-pem")
    order = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
    session.commit()
    r = client.post(
        "/api/payment/notify",
        data={
            "out_trade_no": order.out_trade_no,
            "trade_no": "alipay-api-sig",
            "amount": "199.00",
            "sign": "bad-signature",
        },
    )
    assert r.text == "fail"
    session.refresh(order)
    assert order.status == OrderStatus.PENDING


def test_notify_idempotent(client, session, user):
    order = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
    session.commit()
    data = {
        "out_trade_no": order.out_trade_no,
        "trade_no": "alipay-api-4",
        "amount": "199.00",
    }
    assert client.post("/api/payment/notify", data=data).text == "success"
    assert client.post("/api/payment/notify", data=data).text == "success"


def test_subscribe_updates_role_via_api(client, session, user):
    from sqlalchemy import select

    from app.models import User

    order = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
    session.commit()
    client.post(
        "/api/payment/notify",
        data={
            "out_trade_no": order.out_trade_no,
            "trade_no": "alipay-api-5",
            "amount": "199.00",
        },
    )
    u = session.scalar(select(User).where(User.id == user.id))
    assert u.role == UserRole.PRO


def test_scenario_order_grants_access_via_api(client, session, user, seeded_scenario):
    from sqlalchemy import select

    from app.models import Scenario

    sc = session.scalar(select(Scenario).where(Scenario.id == "it_procurement"))
    sc.price = 99.0
    session.commit()
    order = create_order(
        session, user.id, OrderType.SCENARIO, "it_procurement", 99.0
    )
    session.commit()
    client.post(
        "/api/payment/notify",
        data={
            "out_trade_no": order.out_trade_no,
            "trade_no": "alipay-api-6",
            "amount": "99.00",
        },
    )
    access = session.scalar(
        select(UserScenarioAccess).where(
            UserScenarioAccess.user_id == user.id,
            UserScenarioAccess.scenario_id == "it_procurement",
        )
    )
    assert access is not None


# ---- 订单状态查询（真实支付前端轮询，PRD 7.5）----


def _auth_user_id(session):
    """auth fixture 注册的用户 id（pay@example.com）。"""
    from sqlalchemy import select

    from app.models import User

    return session.scalar(select(User).where(User.email == "pay@example.com")).id


def test_get_order_requires_auth(client):
    assert client.get("/api/payment/orders/whatever").status_code == 401


def test_get_order_returns_pending(client, auth, session):
    order = create_order(session, _auth_user_id(session), OrderType.SUBSCRIBE, None, 199.0)
    session.commit()
    r = client.get(f"/api/payment/orders/{order.id}", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(order.id)
    assert body["out_trade_no"] == order.out_trade_no
    assert body["type"] == "subscribe"
    assert body["amount"] == 199.0
    assert body["status"] == "pending"


def test_get_order_reflects_paid_after_notify(client, auth, session):
    order = create_order(session, _auth_user_id(session), OrderType.SUBSCRIBE, None, 199.0)
    session.commit()
    client.post(
        "/api/payment/notify",
        data={
            "out_trade_no": order.out_trade_no,
            "trade_no": "alipay-api-poll-1",
            "amount": "199.00",
        },
    )
    r = client.get(f"/api/payment/orders/{order.id}", headers=auth)
    assert r.json()["status"] == "paid"


def test_get_order_hides_other_users_order(client, auth, session):
    """订单归属校验：他人订单不暴露（404）。"""
    other = create_order(session, _auth_user_id(session), OrderType.SUBSCRIBE, None, 199.0)
    session.commit()
    client.post(
        "/api/auth/register",
        json={"username": "other", "email": "other@example.com", "password": "password123"},
    )
    tok = client.post(
        "/api/auth/login",
        json={"account": "other@example.com", "password": "password123"},
    ).json()["access_token"]
    r = client.get(
        f"/api/payment/orders/{other.id}",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 404


def test_get_order_unknown_returns_404(client, auth):
    r = client.get("/api/payment/orders/00000000-0000-0000-0000-000000000000", headers=auth)
    assert r.status_code == 404


def test_notify_pushes_to_online_user(client, session, user, monkeypatch):
    """PRD 9.15：支付成功后向在线用户 WS 推送通知。"""
    from app.services.ws_manager import get_ws_manager

    pushed = []

    async def _fake_send_to_user(user_id, message):
        pushed.append((user_id, message))

    monkeypatch.setattr(get_ws_manager(), "send_to_user", _fake_send_to_user)
    order = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
    session.commit()
    r = client.post(
        "/api/payment/notify",
        data={
            "out_trade_no": order.out_trade_no,
            "trade_no": "alipay-api-push-1",
            "amount": "199.00",
        },
    )
    assert r.text == "success"
    assert pushed, "支付成功应触发在线用户推送"
    uid, msg = pushed[0]
    assert str(uid) == str(user.id)
    assert msg["type"] == "notification"
    assert msg["notification"]["type"] == "payment"
