"""支付宝密钥加载兼容层测试：PEM 与无头 base64（沙箱导出格式）都能用。

覆盖：无头 PKCS#8 私钥签名 / 无头公钥验签 / PEM 兼容 / 非法密钥报错 /
签名-验签闭环（含中文 content）。
"""

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.alipay_crypto import _load_private_key, _load_public_key, rsa2_sign, rsa2_verify


@pytest.fixture
def key_pair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pem_public = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    der_private = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    der_public = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "pem_private": pem_private,
        "pem_public": pem_public,
        "raw_private": base64.b64encode(der_private).decode(),  # 无头 base64（沙箱导出）
        "raw_public": base64.b64encode(der_public).decode(),
        "raw_private_nopad": base64.b64encode(der_private).decode().rstrip("="),
        "raw_public_nopad": base64.b64encode(der_public).decode().rstrip("="),
    }


class TestLoadKeys:
    def test_load_raw_private_key(self, key_pair):
        assert _load_private_key(key_pair["raw_private"]) is not None

    def test_load_raw_public_key(self, key_pair):
        assert _load_public_key(key_pair["raw_public"]) is not None

    def test_load_pem_private_key(self, key_pair):
        assert _load_private_key(key_pair["pem_private"]) is not None

    def test_load_pem_public_key(self, key_pair):
        assert _load_public_key(key_pair["pem_public"]) is not None

    def test_invalid_raw_private_key_raises(self):
        with pytest.raises(ValueError):
            _load_private_key("not-a-valid-base64!!!")

    def test_invalid_raw_public_key_raises(self):
        with pytest.raises(ValueError):
            _load_public_key("bm90LWEtY3J5cHRvLWNhdC1rZXk=")

    def test_load_private_key_without_trailing_padding(self, key_pair):
        """沙箱导出省略 = padding 也应能加载。"""
        assert _load_private_key(key_pair["raw_private_nopad"]) is not None

    def test_load_public_key_without_trailing_padding(self, key_pair):
        assert _load_public_key(key_pair["raw_public_nopad"]) is not None


class TestSignVerify:
    def test_raw_keys_sign_verify_roundtrip(self, key_pair):
        content = 'app_id=9021000164692993&biz_content={"total_amount": "199.00"}'
        sign = rsa2_sign(content, key_pair["raw_private"])
        assert rsa2_verify(content, key_pair["raw_public"], sign) is True

    def test_nopad_keys_sign_verify_roundtrip(self, key_pair):
        """无 = padding 的密钥（沙箱导出格式）签名验签闭环。"""
        sign = rsa2_sign("a=1", key_pair["raw_private_nopad"])
        assert rsa2_verify("a=1", key_pair["raw_public_nopad"], sign) is True

    def test_pem_keys_sign_verify_roundtrip(self, key_pair):
        sign = rsa2_sign("a=1", key_pair["pem_private"])
        assert rsa2_verify("a=1", key_pair["pem_public"], sign) is True

    def test_cross_format_verify(self, key_pair):
        """无头私钥签名，PEM 公钥验签（格式互不依赖）。"""
        sign = rsa2_sign("x=中文内容", key_pair["raw_private"])
        assert rsa2_verify("x=中文内容", key_pair["pem_public"], sign) is True

    def test_tampered_content_rejected(self, key_pair):
        sign = rsa2_sign("amount=199.00", key_pair["raw_private"])
        assert rsa2_verify("amount=999.00", key_pair["raw_public"], sign) is False

    def test_invalid_sign_b64_rejected(self, key_pair):
        assert rsa2_verify("a=1", key_pair["raw_public"], "!!!") is False

    def test_wrong_key_rejected(self, key_pair):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_der = other.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        sign = rsa2_sign("a=1", key_pair["raw_private"])
        assert (
            rsa2_verify("a=1", base64.b64encode(other_der).decode(), sign) is False
        )
