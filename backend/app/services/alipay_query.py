"""支付宝主动查单 alipay.trade.query（PRD 7.5 真实对账）。

官方规范（openapi.alipay.com/gateway.do）：
- 公共参数：app_id / method=alipay.trade.query / charset / sign_type=RSA2 /
  timestamp(yyyy-MM-dd HH:mm:ss) / version=1.0 / biz_content(JSON)
- 请求参数（含 biz_content）按 key ASCII 升序拼接 k=v&k2=v2，RSA2 签名
- 响应 JSON：{"alipay_trade_query_response": {...}, "sign": "..."}，配置公钥时验签

降级约定（对齐 MockLLM / Mock 支付宝回调）：
- 未配置 app_id 或应用私钥 → 返回 None（对账跳过该单，不误授权）
- 网络异常 / 非 200 / code != 10000 / 验签失败 → 返回 None（下次对账再试）
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import httpx

from app.core.config import get_settings
from app.services.alipay_crypto import rsa2_sign, rsa2_verify

logger = logging.getLogger(__name__)

GATEWAY = "https://openapi.alipay.com/gateway.do"
API_METHOD = "alipay.trade.query"


def _sign_content(params: dict) -> str:
    """请求签名串：排除 sign，非空值，key ASCII 升序，k=v&k2=v2。"""
    items = sorted(
        (str(k), str(v))
        for k, v in params.items()
        if k != "sign" and str(v) != ""
    )
    return "&".join(f"{k}={v}" for k, v in items)


def _verify_response_sign(response: dict, public_key_value: str) -> bool:
    """支付宝响应验签：sign 与 alipay_trade_query_response 内容匹配。"""
    sign = response.get("sign")
    content = response.get("alipay_trade_query_response")
    if not sign or not isinstance(content, str):
        return False
    try:
        return rsa2_verify(content, public_key_value, sign)
    except Exception as exc:  # noqa: BLE001 验签异常一律视为失败
        logger.warning("支付宝查单响应验签异常: %s", exc)
        return False


def _build_request(out_trade_no: str, settings) -> dict:
    """构造带签名的公共参数 + biz_content（官方格式）。"""
    biz_content = json.dumps({"out_trade_no": out_trade_no}, ensure_ascii=False)
    params = {
        "app_id": settings.alipay_app_id,
        "method": API_METHOD,
        "format": "JSON",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "biz_content": biz_content,
    }
    params["sign"] = rsa2_sign(_sign_content(params), settings.alipay_private_key)
    return params


def _parse_response(payload: dict, settings) -> dict | None:
    resp = payload.get("alipay_trade_query_response") or {}
    if settings.alipay_public_key and not _verify_response_sign(payload, settings.alipay_public_key):
        logger.warning("支付宝查单响应验签失败，拒绝采信")
        return None
    if resp.get("code") != "10000":
        logger.warning(
            "支付宝查单业务失败: sub_code=%s sub_msg=%s",
            resp.get("sub_code"),
            resp.get("sub_msg"),
        )
        return None
    return {
        "out_trade_no": resp.get("out_trade_no"),
        "trade_no": resp.get("trade_no"),
        "trade_status": resp.get("trade_status"),
        "total_amount": resp.get("total_amount"),
    }


def query_trade(out_trade_no: str) -> dict | None:
    """调用 alipay.trade.query 查询订单状态。

    返回 {"out_trade_no", "trade_no", "trade_status", "total_amount"}；
    未配置密钥 / 网络失败 / 业务失败 / 验签失败 → None。
    """
    settings = get_settings()
    if not settings.alipay_app_id or not settings.alipay_private_key:
        logger.info("支付宝查单未配置（app_id/私钥），降级跳过: %s", out_trade_no)
        return None

    params = _build_request(out_trade_no, settings)
    gateway = settings.alipay_gateway or GATEWAY
    try:
        response = httpx.post(gateway, data=params, timeout=10)
    except Exception as exc:  # noqa: BLE001 网络异常降级，下次对账再试
        logger.warning("支付宝查单网络异常: %s (%s)", out_trade_no, exc)
        return None
    if response.status_code != 200:
        logger.warning("支付宝查单 HTTP %s: %s", response.status_code, out_trade_no)
        return None
    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("支付宝查单响应非 JSON: %s", exc)
        return None
    return _parse_response(payload, settings)
