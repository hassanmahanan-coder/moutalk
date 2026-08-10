"""支付宝电脑网站支付 alipay.trade.page.pay（PRD 7.5 真实支付跳转）。

官方规范（opendocs.alipay.com/open/59da99d0_alipay.trade.page.pay）：
- 页面跳转型接口：为商户生成带签名的 GET 跳转 URL（浏览器打开即收银台）
- 公共参数：app_id / method=alipay.trade.page.pay / charset / sign_type /
  timestamp / version / notify_url / return_url + biz_content(JSON)
- biz_content 必填：out_trade_no / total_amount（元，两位小数）/
  subject / product_code=FAST_INSTANT_TRADE_PAY
- 支付结果以异步通知 / alipay.trade.query 为准，不能依赖同步跳转

降级约定：未配置 app_id 或应用私钥 → 返回 None（前端提示支付暂不可用）。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from urllib.parse import quote

from app.core.config import get_settings
from app.services.alipay_crypto import rsa2_sign

logger = logging.getLogger(__name__)

API_METHOD = "alipay.trade.page.pay"
PRODUCT_CODE = "FAST_INSTANT_TRADE_PAY"


def _sign_content(params: dict) -> str:
    """请求签名串：排除 sign/sign_type，非空值，key ASCII 升序，k=v&k2=v2。"""
    items = sorted(
        (str(k), str(v))
        for k, v in params.items()
        if k not in ("sign", "sign_type") and str(v) != ""
    )
    return "&".join(f"{k}={v}" for k, v in items)


def _build_params(
    out_trade_no: str, amount: float, subject: str, settings
) -> dict:
    biz_content = json.dumps(
        {
            "out_trade_no": out_trade_no,
            "total_amount": f"{amount:.2f}",
            "subject": subject,
            "product_code": PRODUCT_CODE,
        },
        ensure_ascii=False,
    )
    return {
        "app_id": settings.alipay_app_id,
        "method": API_METHOD,
        "format": "JSON",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "notify_url": settings.alipay_notify_url,
        "biz_content": biz_content,
    }


def build_pay_url(out_trade_no: str, amount: float, subject: str) -> str | None:
    """生成 alipay.trade.page.pay 支付跳转 URL；未配置密钥返回 None。

    签名基于未编码原始参数值（官方 pageExecute GET：先拼签名串再整体
    URL 编码进链接，服务端解码后验签）。
    """
    settings = get_settings()
    if not settings.alipay_app_id or not settings.alipay_private_key:
        logger.info("支付宝支付未配置（app_id/私钥），跳过生成: %s", out_trade_no)
        return None

    params = _build_params(out_trade_no, amount, subject, settings)
    params["sign"] = rsa2_sign(_sign_content(params), settings.alipay_private_key)
    query = "&".join(
        f"{k}={quote(str(v), safe='')}" for k, v in params.items()
    )
    return f"{settings.alipay_gateway}?{query}"
