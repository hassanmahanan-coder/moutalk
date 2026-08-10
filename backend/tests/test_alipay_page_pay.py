"""支付宝电脑网站支付 alipay.trade.page.pay 测试（PRD 7.5 真实支付跳转）。

覆盖：未配置密钥降级、URL 构造（公共参数+签名+notify_url）、
biz_content 必填字段、金额格式、签名可被验签函数验证。
"""

from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

PAGE_PAY_MODULE = "app.services.alipay_page_pay"

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
        "alipay_app_id": "9021000164692993",
        "alipay_private_key": PRIVATE_KEY,
        "alipay_public_key": PUBLIC_KEY,
        "alipay_gateway": "https://openapi.alipaydev.com/gateway.do",
        "alipay_notify_url": "https://example.com/api/payment/notify",
    }
    base.update(overrides)
    return Mock(**base)


def _parse_pay_url(url: str) -> dict:
    parsed = urlparse(url)
    return {k: v[0] for k, v in parse_qs(parsed.query).items()}


class TestBuildPayUrl:
    def test_degrades_when_keys_not_configured(self):
        """未配置 app_id/私钥 → 返回 None（前端可降级提示）。"""
        settings = Mock(
            alipay_app_id="", alipay_private_key="", alipay_public_key=""
        )
        with patch(f"{PAGE_PAY_MODULE}.get_settings", return_value=settings):
            from app.services.alipay_page_pay import build_pay_url

            assert build_pay_url("MT123", 199.0, "Pro 订阅") is None

    def test_builds_signed_get_url_with_public_params(self):
        from app.services.alipay_page_pay import build_pay_url

        with patch(f"{PAGE_PAY_MODULE}.get_settings", return_value=_settings()):
            url = build_pay_url("MT123", 199.0, "Pro 订阅")

        assert url.startswith("https://openapi.alipaydev.com/gateway.do?")
        q = _parse_pay_url(url)
        assert q["app_id"] == "9021000164692993"
        assert q["method"] == "alipay.trade.page.pay"
        assert q["sign_type"] == "RSA2"
        assert q["version"] == "1.0"
        assert q["charset"] == "utf-8"
        assert q["notify_url"] == "https://example.com/api/payment/notify"
        assert q["sign"]  # 请求已签名

    def test_biz_content_contains_required_fields(self):
        """官方必填：out_trade_no / total_amount / subject / product_code。"""
        import json

        from app.services.alipay_page_pay import build_pay_url

        with patch(f"{PAGE_PAY_MODULE}.get_settings", return_value=_settings()):
            url = build_pay_url("MT123", 199.0, "Pro 订阅")

        biz = json.loads(_parse_pay_url(url)["biz_content"])
        assert biz["out_trade_no"] == "MT123"
        assert biz["total_amount"] == "199.00"  # 金额两位小数
        assert biz["subject"] == "Pro 订阅"
        assert biz["product_code"] == "FAST_INSTANT_TRADE_PAY"

    def test_amount_formatted_to_two_decimals(self):
        import json

        from app.services.alipay_page_pay import build_pay_url

        with patch(f"{PAGE_PAY_MODULE}.get_settings", return_value=_settings()):
            url = build_pay_url("MT456", 0.1, "场景包")

        biz = json.loads(_parse_pay_url(url)["biz_content"])
        assert biz["total_amount"] == "0.10"

    def test_signature_verifies_with_public_key(self):
        """请求签名可用支付宝验签逻辑反向验证（RSA2 SHA256）。

        签名基于未编码原始参数值（官方 pageExecute GET 模式），
        URL 只是传输编码，因此用解码后的值重建签名串验签。
        """
        from app.services.alipay_page_pay import build_pay_url
        from app.services.alipay_verify import _build_sign_content, _verify_sha256_rsa

        with patch(f"{PAGE_PAY_MODULE}.get_settings", return_value=_settings()):
            url = build_pay_url("MT123", 199.0, "Pro 订阅")

        q = _parse_pay_url(url)
        sign = q.pop("sign")
        assert _verify_sha256_rsa(_build_sign_content(q), PUBLIC_KEY, sign) is True

    def test_tampered_params_invalidates_signature(self):
        """签名覆盖全部公共参数 + biz_content：篡改金额后验签失败。"""
        from app.services.alipay_page_pay import build_pay_url
        from app.services.alipay_verify import _build_sign_content, _verify_sha256_rsa

        with patch(f"{PAGE_PAY_MODULE}.get_settings", return_value=_settings()):
            url = build_pay_url("MT123", 199.0, "Pro 订阅")

        q = _parse_pay_url(url)
        sign = q.pop("sign")
        q["biz_content"] = q["biz_content"].replace("199.00", "999.00")
        assert _verify_sha256_rsa(_build_sign_content(q), PUBLIC_KEY, sign) is False
