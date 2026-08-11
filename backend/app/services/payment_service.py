"""支付服务：订单创建 + 回调处理（幂等 / 金额校验 / 权限更新）。

PRD 7.5 / 9.12：
- 创建订单：orders 表（pending）→ 支付宝沙箱支付链接（MVP 为 Mock）
- 回调：验签（MVP 简化）→ 幂等（payment_log trade_no UNIQUE）→
  订单匹配 → 金额校验 → 事务更新订单 + 用户权限
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Order,
    OrderStatus,
    OrderType,
    PaymentLog,
    User,
    UserRole,
    UserScenarioAccess,
)

logger = logging.getLogger(__name__)

PRO_DAYS = 30  # Pro 订阅时长（天）


class PaymentError(Exception):
    pass


def _gen_out_trade_no() -> str:
    return f"MT{uuid.uuid4().hex.upper()[:24]}"


def create_order(
    db: Session,
    user_id: uuid.UUID,
    order_type: OrderType,
    target_id: str | None,
    amount: float,
) -> Order:
    """创建待支付订单，返回订单记录。"""
    order = Order(
        user_id=user_id,
        type=order_type,
        target_id=target_id,
        amount=round(amount, 2),
        out_trade_no=_gen_out_trade_no(),
    )
    db.add(order)
    db.flush()
    return order


def _log_received(db: Session, trade_no: str) -> bool:
    """幂等检查：trade_no 已收过返回 False，否则记录。"""
    exists = db.scalar(select(PaymentLog).where(PaymentLog.trade_no == trade_no))
    if exists is not None:
        return False
    db.add(PaymentLog(trade_no=trade_no))
    return True


def _grant_entitlement(db: Session, order: Order) -> None:
    """按订单类型更新用户权限（PRD 7.5）。"""
    if order.type == OrderType.SUBSCRIBE:
        user = db.get(User, order.user_id)
        if user is not None:
            user.role = UserRole.PRO
            user.expire_at = datetime.now(UTC) + timedelta(days=PRO_DAYS)
        return
    if order.type == OrderType.SCENARIO and order.target_id:
        db.add(
            UserScenarioAccess(
                user_id=order.user_id,
                scenario_id=order.target_id,
            )
        )


def process_paid_callback(
    db: Session,
    out_trade_no: str,
    trade_no: str,
    amount: float,
) -> bool:
    """处理支付成功回调。返回是否成功（False = 忽略）。

    顺序（PRD 9.12）：幂等 → 订单匹配 → 金额校验 → 单事务更新。
    """
    if not _log_received(db, trade_no):
        return True  # 重复回调：已处理过，视为成功（幂等）

    order = db.scalar(select(Order).where(Order.out_trade_no == out_trade_no))
    if order is None:
        logger.warning("支付回调订单不存在: %s", out_trade_no)
        return False

    if order.status == OrderStatus.PAID:
        return True

    if float(order.amount) != round(float(amount), 2):
        logger.warning(
            "支付回调金额不匹配: order=%s expect=%s got=%s",
            out_trade_no,
            order.amount,
            amount,
        )
        return False

    order.status = OrderStatus.PAID
    order.trade_no = trade_no
    order.paid_at = datetime.now(UTC)
    _grant_entitlement(db, order)
    db.commit()
    # PRD 9.15 双写：支付成功落库离线通知 + 发布事件（在线 WS 推送，离线拉取）
    try:
        from app.services.event_bus import publish_notification
        from app.services.notification_service import create_notification

        create_notification(
            db,
            order.user_id,
            "payment",
            "支付成功",
            {"order_id": str(order.id), "out_trade_no": order.out_trade_no},
        )
        db.commit()
        publish_notification(
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
    except Exception as exc:  # noqa: BLE001 通知落库失败不阻断支付
        logger.warning("支付成功通知落库失败: %s", exc)
        db.rollback()
    logger.info("支付回调成功: %s", out_trade_no)
    return True


def reconcile_pending_payments(
    db: Session,
    query_order: Callable[[str], dict] | None = None,
    timeout_minutes: int = 30,
) -> dict:
    """主动对账（PRD 7.5）：扫描超时 PENDING 订单，向支付宝查单补登记。

    - `query_order(out_trade_no)` 返回支付宝查单结果（含 trade_no / trade_status /
      total_amount）；返回 None 或抛异常视为该单无法核实，跳过（不误授权）
    - 未传 query_order 时默认走真实 alipay.trade.query（未配置密钥自动降级 None）
    - 已支付（TRADE_SUCCESS）且金额一致 → 复用 process_paid_callback 幂等补登
    - 返回统计 {"scanned", "reconciled", "skipped"} 供告警
    """
    if query_order is None:
        from app.services.alipay_query import query_trade

        query_order = query_trade

    scanned = reconciled = skipped = 0
    cutoff = datetime.now(UTC) - timedelta(minutes=timeout_minutes)

    orders = db.scalars(
        select(Order).where(
            Order.status == OrderStatus.PENDING,
            Order.created_at < cutoff,
        )
    ).all()

    for order in orders:
        scanned += 1
        try:
            result = query_order(order.out_trade_no)
        except Exception:  # noqa: BLE001 查单失败的单跳过，下次对账再试
            logger.warning("主动对账查单失败: %s", order.out_trade_no)
            skipped += 1
            continue
        if not result or result.get("trade_status") != "TRADE_SUCCESS":
            skipped += 1
            continue
        amount = result.get("total_amount")
        try:
            ok = process_paid_callback(
                db,
                order.out_trade_no,
                str(result["trade_no"]),
                float(amount) if amount is not None else float(order.amount),
            )
        except Exception:  # noqa: BLE001 补登异常不阻断对账
            logger.warning("主动对账补登异常: %s", order.out_trade_no)
            skipped += 1
            continue
        if ok:
            reconciled += 1
        else:
            skipped += 1

    logger.info(
        "主动对账完成: scanned=%s reconciled=%s skipped=%s",
        scanned,
        reconciled,
        skipped,
    )
    return {"scanned": scanned, "reconciled": reconciled, "skipped": skipped}
