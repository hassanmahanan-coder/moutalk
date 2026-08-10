"""支付宝异步回调 RSA2 验签测试（PRD 9.12）：真实密钥验签、篡改拒绝、缺配置降级。"""

import base64
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.services.alipay_verify import verify_notify


def _make_keys(pem_public: bool = True):
    """生成测试用 RSA 密钥对，返回 (public_key_pem, private_key_pem)。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_key = key.public_key()
    if pem_public:
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
    else:
        # 支付宝公钥是"-----BEGIN PUBLIC KEY-----"格式（SubjectPublicKeyInfo）
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
    return public_pem, private_pem


def _sign_content(params: dict, private_key_pem: str) -> str:
    """按支付宝规范构造签名串并 RSA-SHA256 签名（与生产实现对称）。"""
    # 排除 sign / sign_type，其余按 key ASCII 升序
    items = sorted((k, v) for k, v in params.items() if k not in ("sign", "sign_type") and v != "")
    content = "&".join(f"{k}={v}" for k, v in items)
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(), password=None
    )
    sig = private_key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


PUBLIC_KEY, PRIVATE_KEY = _make_keys()


def _valid_params() -> dict:
    return {
        "notify_type": "trade_status_sync",
        "trade_status": "TRADE_SUCCESS",
        "out_trade_no": "MTTEST0001",
        "trade_no": "2026080122001",
        "total_amount": "199.00",
        "app_id": "9021000164692993",
        "sign_type": "RSA2",
    }


def _signed_params() -> dict:
    params = _valid_params()
    params["sign"] = _sign_content(params, PRIVATE_KEY)
    return params


class TestVerifyNotify:
    def test_valid_signature_passes(self):
        params = _signed_params()
        with patch("app.services.alipay_verify._get_public_key", return_value=PUBLIC_KEY):
            assert verify_notify(params) is True

    def test_tampered_amount_rejected(self):
        params = _signed_params()
        params["total_amount"] = "99999.00"  # 篡改金额后签名不变
        with patch("app.services.alipay_verify._get_public_key", return_value=PUBLIC_KEY):
            assert verify_notify(params) is False

    def test_tampered_out_trade_no_rejected(self):
        params = _signed_params()
        params["out_trade_no"] = "MTHACKED"
        with patch("app.services.alipay_verify._get_public_key", return_value=PUBLIC_KEY):
            assert verify_notify(params) is False

    def test_missing_sign_rejected(self):
        params = _valid_params()  # 无 sign 字段
        with patch("app.services.alipay_verify._get_public_key", return_value=PUBLIC_KEY):
            assert verify_notify(params) is False

    def test_mock_trade_no_skips_sign_check_when_public_key_configured(self):
        """前端 Mock 回调（trade_no 以 mock_ 开头）在配置公钥后仍应放行，
        否则配置沙箱密钥后模拟支付流程会因缺 sign 被拒（回归 bug）。"""
        params = _valid_params()
        params["trade_no"] = "mock_1723000000000"
        params.pop("sign", None)
        with patch("app.services.alipay_verify._get_public_key", return_value=PUBLIC_KEY):
            assert verify_notify(params) is True

    def test_mock_trade_no_still_rejected_when_sign_present_but_invalid(self):
        """mock_ 前缀仅豁免『缺 sign』；带伪造 sign 仍必须验签拒绝。"""
        params = _valid_params()
        params["trade_no"] = "mock_1723000000000"
        params["sign"] = "forged-signature"
        with patch("app.services.alipay_verify._get_public_key", return_value=PUBLIC_KEY):
            assert verify_notify(params) is False

    def test_sign_field_excluded_from_content(self):
        """sign 字段不应参与排序拼接，只做签名内容校验。"""
        params = _signed_params()
        # 额外加一个合法无符号字段：不影响验签（因为签名串只含已签名参数）
        params["extra_noise"] = "x"
        with patch("app.services.alipay_verify._get_public_key", return_value=PUBLIC_KEY):
            # 加噪参数不打进签名 → 默认应拒绝（支付宝未签名字段回调实际不含）
            assert verify_notify(params) is False

    def test_degraded_true_when_no_public_key_configured(self):
        """未配置公钥（MVP 阶段）时降级放行，保证沙箱 Mock 回调可跑。"""
        params = _valid_params()
        with patch("app.services.alipay_verify._get_public_key", return_value=None):
            assert verify_notify(params) is True

    def test_blank_public_key_degraded(self):
        with patch("app.services.alipay_verify._get_public_key", return_value=""):
            assert verify_notify(_valid_params()) is True