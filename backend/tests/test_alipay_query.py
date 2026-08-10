"""支付宝主动查单 alipay.trade.query 测试（PRD 7.5 真实对账）。

覆盖：未配置密钥降级、请求构造（公共参数+签名）、响应解析、
响应验签失败拒绝、网络异常降级、code 非成功拒绝。
"""

from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.models import Order, OrderStatus, OrderType
from app.services.payment_service import create_order, reconcile_pending_payments

QUERY_MODULE = "app.services.alipay_query"

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_KEY = _key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
PUBLIC_KEY = _key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()


def _settings(**overrides):
    base = {
        "alipay_app_id": "2021000000000000",
        "alipay_private_key": PRIVATE_KEY,
        "alipay_public_key": "",
        "alipay_gateway": "https://openapi.alipaydev.com/gateway.do",
    }
    base.update(overrides)
    return Mock(**base)


class TestQueryTradeConfig:
    def test_degrades_when_keys_not_configured(self, monkeypatch):
        """未配置 app_id/私钥（Mock 环境）→ 返回 None（对账走降级跳过）。"""
        settings = Mock(
            alipay_app_id="", alipay_private_key="", alipay_public_key=""
        )
        with patch(f"{QUERY_MODULE}.get_settings", return_value=settings):
            from app.services.alipay_query import query_trade

            assert query_trade("MT123") is None

    def test_requires_private_key_when_app_id_set(self, monkeypatch):
        """只配 app_id 没配私钥 → 视为未配置，降级 None（不抛错）。"""
        settings = Mock(
            alipay_app_id="2021000000000000", alipay_private_key="", alipay_public_key=""
        )
        with patch(f"{QUERY_MODULE}.get_settings", return_value=settings):
            from app.services.alipay_query import query_trade

            assert query_trade("MT123") is None


class TestQueryTradeRequest:
    def test_sends_signed_public_params_and_biz_content(self, monkeypatch):
        """请求含公共参数 + 签名 + biz_content（官方规范：method/alipay.trade.query）。"""
        settings = _settings()
        sent = {}

        def fake_post(url, data=None, timeout=None):
            sent["url"] = url
            sent["data"] = data or {}
            return Mock(
                status_code=200,
                json=lambda: {
                    "alipay_trade_query_response": {
                        "code": "10000",
                        "msg": "Success",
                        "trade_no": "202608010001",
                        "out_trade_no": "MT123",
                        "trade_status": "TRADE_SUCCESS",
                        "total_amount": "199.00",
                    },
                    "sign": "sig",
                },
            )

        with patch(f"{QUERY_MODULE}.get_settings", return_value=settings), patch(
            f"{QUERY_MODULE}.httpx.post", side_effect=fake_post
        ) as post:
            from app.services.alipay_query import query_trade

            query_trade("MT123")

        assert sent["url"] == "https://openapi.alipaydev.com/gateway.do"
        data = sent["data"]
        assert data["method"] == "alipay.trade.query"
        assert data["app_id"] == "2021000000000000"
        assert data["sign_type"] == "RSA2"
        assert data["version"] == "1.0"
        assert data["charset"] == "utf-8"
        assert data["sign"]  # 请求已签名
        import json

        assert json.loads(data["biz_content"]) == {"out_trade_no": "MT123"}
        post.assert_called_once()


class TestQueryTradeResponse:
    def test_returns_success_response_fields(self, monkeypatch):
        settings = _settings()
        with patch(f"{QUERY_MODULE}.get_settings", return_value=settings), patch(
            f"{QUERY_MODULE}.httpx.post",
            return_value=Mock(
                status_code=200,
                json=lambda: {
                    "alipay_trade_query_response": {
                        "code": "10000",
                        "msg": "Success",
                        "trade_no": "202608010001",
                        "out_trade_no": "MT123",
                        "trade_status": "TRADE_SUCCESS",
                        "total_amount": "199.00",
                    },
                    "sign": "sig",
                },
            ),
        ):
            from app.services.alipay_query import query_trade

            result = query_trade("MT123")
        assert result == {
            "out_trade_no": "MT123",
            "trade_no": "202608010001",
            "trade_status": "TRADE_SUCCESS",
            "total_amount": "199.00",
        }

    def test_rejects_business_error_code(self, monkeypatch):
        """code != 10000（如 ACQ.TRADE_NOT_EXIST）→ None，不误认为未支付。"""
        settings = _settings()
        with patch(f"{QUERY_MODULE}.get_settings", return_value=settings), patch(
            f"{QUERY_MODULE}.httpx.post",
            return_value=Mock(
                status_code=200,
                json=lambda: {
                    "alipay_trade_query_response": {
                        "code": "40004",
                        "msg": "Business Failed",
                        "sub_code": "ACQ.TRADE_NOT_EXIST",
                        "sub_msg": "交易不存在",
                    },
                    "sign": "sig",
                },
            ),
        ):
            from app.services.alipay_query import query_trade

            assert query_trade("MT123") is None

    def test_returns_none_on_network_error(self, monkeypatch):
        settings = _settings()
        with patch(f"{QUERY_MODULE}.get_settings", return_value=settings), patch(
            f"{QUERY_MODULE}.httpx.post", side_effect=Exception("network down")
        ):
            from app.services.alipay_query import query_trade

            assert query_trade("MT123") is None

    def test_rejects_non_200_response(self, monkeypatch):
        settings = _settings()
        with patch(f"{QUERY_MODULE}.get_settings", return_value=settings), patch(
            f"{QUERY_MODULE}.httpx.post",
            return_value=Mock(status_code=500, json=dict),
        ):
            from app.services.alipay_query import query_trade

            assert query_trade("MT123") is None


class TestQueryTradeSignature:
    def test_rejects_response_with_bad_signature(self, monkeypatch):
        """配置公钥时响应验签失败 → None（防中间人/篡改）。"""
        settings = _settings(alipay_public_key="bad-public-key")
        with patch(f"{QUERY_MODULE}.get_settings", return_value=settings), patch(
            f"{QUERY_MODULE}.httpx.post",
            return_value=Mock(
                status_code=200,
                json=lambda: {
                    "alipay_trade_query_response": {
                        "code": "10000",
                        "msg": "Success",
                        "trade_status": "TRADE_SUCCESS",
                    },
                    "sign": "tampered-sign",
                },
            ),
        ):
            from app.services.alipay_query import query_trade

            assert query_trade("MT123") is None


class TestReconcileWithRealQuery:
    def test_task_reconciles_using_real_query(self, session, user):
        """task 接入真实查单：TRADE_SUCCESS 补登授权（金额一致）。"""
        from datetime import UTC
        from datetime import datetime as dt
        from datetime import timedelta as td

        from sqlalchemy.orm import sessionmaker

        order = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
        order.created_at = dt.now(UTC) - td(minutes=60)
        session.commit()

        Session = sessionmaker(bind=session.get_bind(), autoflush=False)

        from app.celery_app import reconcile_pending_payments_task

        with patch(
            f"{QUERY_MODULE}.query_trade",
            return_value={
                "out_trade_no": order.out_trade_no,
                "trade_no": "alipay-real-1",
                "trade_status": "TRADE_SUCCESS",
                "total_amount": "199.00",
            },
        ), patch("app.celery_app.SessionLocal", new=Session):
            stats = reconcile_pending_payments_task.run(timeout_minutes=30)

        assert stats == {"scanned": 1, "reconciled": 1, "skipped": 0}
        session.expire_all()
        assert session.get(Order, order.id).status == OrderStatus.PAID

    def test_reconcile_core_uses_default_query_when_none(self, session, user, monkeypatch):
        """reconcile_pending_payments 未传 query_order 时默认走真实 query_trade。"""
        from datetime import UTC
        from datetime import datetime as dt
        from datetime import timedelta as td

        order = create_order(session, user.id, OrderType.SUBSCRIBE, None, 199.0)
        order.created_at = dt.now(UTC) - td(minutes=60)
        session.commit()


        with patch(
            f"{QUERY_MODULE}.query_trade",
            return_value={
                "out_trade_no": order.out_trade_no,
                "trade_no": "alipay-real-2",
                "trade_status": "TRADE_SUCCESS",
                "total_amount": "199.00",
            },
        ):
            stats = reconcile_pending_payments(session, timeout_minutes=30)

        assert stats["reconciled"] == 1
        session.expire_all()
        assert session.get(Order, order.id).status == OrderStatus.PAID