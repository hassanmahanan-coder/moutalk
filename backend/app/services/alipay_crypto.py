"""支付宝密钥加载兼容层：PEM 与无 PEM 头纯 base64（沙箱导出格式）都能加载。

支付宝沙箱控制台导出的「应用私钥/支付宝公钥」默认是去掉
`-----BEGIN/END ...-----` 头的纯 base64（PKCS#8 私钥 / SubjectPublicKeyInfo
公钥），而 cryptography 的 load_pem_* 只认完整 PEM。本层统一兜底。
"""

from __future__ import annotations

import base64
import logging

logger = logging.getLogger(__name__)


def _b64decode(key_value: str) -> bytes:
    """解码可能缺失尾部 padding 的 base64（沙箱导出常省略 =）。"""
    text = key_value.strip()
    pad = (4 - len(text) % 4) % 4
    return base64.b64decode(text + "=" * pad)


def _load_private_key(key_value: str):
    from cryptography.hazmat.primitives import serialization

    text = key_value.strip()
    if "-----BEGIN" in text:
        return serialization.load_pem_private_key(text.encode("utf-8"), password=None)
    try:
        der = _b64decode(text)
    except Exception as exc:
        raise ValueError(f"应用私钥 base64 解码失败: {exc}") from exc
    try:
        return serialization.load_der_private_key(der, password=None)
    except Exception as exc:
        raise ValueError(f"应用私钥 DER 解析失败: {exc}") from exc


def _load_public_key(key_value: str):
    from cryptography.hazmat.primitives import serialization

    text = key_value.strip()
    if "-----BEGIN" in text:
        return serialization.load_pem_public_key(text.encode("utf-8"))
    try:
        der = _b64decode(text)
    except Exception as exc:
        raise ValueError(f"支付宝公钥 base64 解码失败: {exc}") from exc
    try:
        return serialization.load_der_public_key(der)
    except Exception as exc:
        raise ValueError(f"支付宝公钥 DER 解析失败: {exc}") from exc


def rsa2_sign(content: str, private_key_value: str) -> str:
    """RSA2(SHA256withRSA) 签名，兼容 PEM / 无头 base64 私钥。"""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    key = _load_private_key(private_key_value)
    sig = key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


def rsa2_verify(content: str, public_key_value: str, sign_b64: str) -> bool:
    """RSA2 验签，兼容 PEM / 无头 base64 公钥；异常一律视为不通过。"""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    try:
        key = _load_public_key(public_key_value)
        signature = base64.b64decode(sign_b64)
        key.verify(signature, content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, ValueError) as exc:
        logger.warning("支付宝验签不通过: %s", exc)
        return False
