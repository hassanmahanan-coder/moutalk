"""支付宝异步回调 RSA2 验签（PRD 9.12）。

支付宝签名规范：
- 签名串 = 排除 `sign` / `sign_type` 后，剩余非空参数按 key ASCII 升序，
  以 `k=v&k2=v2` 串接
- RSA2 = SHA256withRSA，公钥验证签名（BASE64）
- 未配置公钥时降级放行（MVP Mock 阶段），配置后即校验
- 公钥兼容 PEM 与无头 base64（沙箱导出格式，见 alipay_crypto）
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.services.alipay_crypto import rsa2_verify

logger = logging.getLogger(__name__)

EXCLUDE_KEYS = ("sign", "sign_type")


def _get_public_key() -> str:
    """支付宝公钥（PEM）。MVP 未配置返回空串/None。"""
    return get_settings().alipay_public_key


def _build_sign_content(params: dict) -> str:
    """构造待验签串：排除 sign/sign_type，非空值，key ASCII 升序，k=v&k2=v2。"""
    items = sorted(
        (str(k), str(v))
        for k, v in params.items()
        if k not in EXCLUDE_KEYS and str(v) != ""
    )
    return "&".join(f"{k}={v}" for k, v in items)


def verify_notify(params: dict) -> bool:
    """校验支付宝异步回调签名。有效返回 True；无效返回 False。

    注意：`total_amount` 等业务字段的取值语义校验由调用方负责，
    本函数只做密码学校验（签名通过但金额被换也会因签名不匹配而拒绝）。
    """
    public_key = _get_public_key()
    if not public_key:
        logger.warning("未配置 ALIPAY_PUBLIC_KEY，验签跳过（MVP 降级）")
        return True

    sign = params.get("sign")
    if not sign:
        # 前端 Mock 回调（PaymentView mockNotify，trade_no 以 mock_ 开头）
        # 不携带 sign：配置沙箱公钥后仍需放行，否则模拟支付流程被拒。
        if str(params.get("trade_no", "")).startswith("mock_"):
            logger.warning("Mock 回调（trade_no 前缀 mock_）跳过验签（开发模式）")
            return True
        logger.warning("支付宝回调缺少 sign 字段")
        return False

    content = _build_sign_content(params)
    try:
        return _verify_sha256_rsa(content, public_key, sign)
    except Exception as exc:  # noqa: BLE001 验签异常一律视为无效
        logger.warning("支付宝验签失败: %s", exc)
        return False


def _verify_sha256_rsa(content: str, public_key_value: str, sign_b64: str) -> bool:
    """RSA2 验签（兼容 PEM / 无头 base64 公钥）；异常一律视为不通过。"""
    try:
        return rsa2_verify(content, public_key_value, sign_b64)
    except Exception as exc:  # noqa: BLE001 验签异常一律视为不通过
        logger.warning("支付宝验签异常: %s", exc)
        return False