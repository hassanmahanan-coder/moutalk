"""支付 API：创建订单 + 支付宝回调验签（PRD 7.5 / 9.12，真实支付宝跳转）。"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import Order, OrderType, Scenario, User
from app.services.alipay_page_pay import build_pay_url
from app.services.alipay_verify import verify_notify
from app.services.payment_service import PaymentError, create_order, process_paid_callback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment", tags=["payment"])

SUBSCRIBE_PRICE = 199.0  # Pro 订阅价格（元/30 天）


def _subject_for(req: CreateOrderRequest, scenario: Scenario | None) -> str:
    if req.type == OrderType.SUBSCRIBE:
        return "MouTalk Pro 月订阅"
    return f"场景包：{(scenario.title if scenario else req.target_id or '')[:20]}"


class CreateOrderRequest(BaseModel):
    type: OrderType
    target_id: str | None = Field(default=None, max_length=64)


def _price_for(db: Session, req: CreateOrderRequest) -> float:
    if req.type == OrderType.SUBSCRIBE:
        return SUBSCRIBE_PRICE
    if not req.target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TARGET_REQUIRED", "message": "购买场景包需指定 target_id"},
        )
    scenario = db.scalar(select(Scenario).where(Scenario.id == req.target_id))
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCENARIO_NOT_FOUND", "message": "场景包不存在"},
        )
    if scenario.price is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SCENARIO_FREE", "message": "该场景包为免费内置，无需购买"},
        )
    return float(scenario.price)


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def create_payment_order(
    req: CreateOrderRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    amount = _price_for(db, req)
    scenario = None
    if req.type == OrderType.SCENARIO and req.target_id:
        scenario = db.scalar(select(Scenario).where(Scenario.id == req.target_id))
    try:
        order = create_order(db, user.id, req.type, req.target_id, amount)
    except PaymentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "PAYMENT_ERROR", "message": str(exc)},
        )
    db.commit()
    pay_url = build_pay_url(
        order.out_trade_no, float(order.amount), _subject_for(req, scenario)
    )
    if pay_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "PAYMENT_NOT_CONFIGURED",
                "message": "支付未配置（缺少支付宝应用密钥），请稍后再试",
            },
        )
    return {
        "id": str(order.id),
        "out_trade_no": order.out_trade_no,
        "type": order.type.value,
        "target_id": order.target_id,
        "amount": float(order.amount),
        "status": order.status.value,
        "pay_url": pay_url,
    }


@router.get("/orders/{order_id}")
def get_payment_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """订单状态查询（真实支付前端轮询）：只返回本人订单，他人/不存在一律 404。"""
    order = db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == user.id,
        )
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": "订单不存在"},
        )
    return {
        "id": str(order.id),
        "out_trade_no": order.out_trade_no,
        "type": order.type.value,
        "target_id": order.target_id,
        "amount": float(order.amount),
        "status": order.status.value,
    }


@router.post("/notify", response_class=PlainTextResponse)
async def alipay_notify(
    out_trade_no: str = Form(...),
    trade_no: str = Form(...),
    amount: str = Form(...),
    sign: str = Form(""),
    sign_type: str = Form(""),
    app_id: str = Form(""),
    trade_status: str = Form(""),
    db: Session = Depends(get_db),
) -> str:
    """支付宝异步回调：RSA2 验签 → 金额校验 + 幂等（PRD 9.12）。

    验签失败返回 fail（支付宝会重试）；未配置公钥时降级放行（MVP Mock）。
    """
    params = {
        "out_trade_no": out_trade_no,
        "trade_no": trade_no,
        "total_amount": amount,
        "sign": sign,
        "sign_type": sign_type,
        "app_id": app_id,
        "trade_status": trade_status,
    }
    if not verify_notify(params):
        logger.warning("支付宝回调验签失败: out_trade_no=%s", out_trade_no)
        return "fail"
    try:
        ok = process_paid_callback(db, out_trade_no, trade_no, float(amount))
    except Exception:  # noqa: BLE001 回调异常统一返回 fail（支付宝会重试）
        return "fail"
    if ok:
        # PRD 9.15 双写：支付成功推送给在线用户（离线由通知落库兜底）
        try:
            order = db.scalar(select(Order).where(Order.out_trade_no == out_trade_no))
            if order is not None:
                from app.services.ws_manager import get_ws_manager

                await get_ws_manager().send_to_user(
                    str(order.user_id),
                    {
                        "type": "notification",
                        "notification": {
                            "type": "payment",
                            "title": "支付成功",
                            "out_trade_no": order.out_trade_no,
                        },
                    },
                )
        except Exception:  # noqa: BLE001 推送失败不阻断回调应答
            logger.warning("支付成功 WS 推送失败: %s", out_trade_no)
    return "success" if ok else "fail"
