import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.db import Base


class OrderType(str, enum.Enum):
    SUBSCRIBE = "subscribe"
    SCENARIO = "scenario"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type", values_callable=lambda e: [m.value for m in e]),
    )
    target_id: Mapped[str | None] = mapped_column(String(64))
    amount: Mapped[Numeric] = mapped_column(Numeric(10, 2))
    out_trade_no: Mapped[str] = mapped_column(unique=True, index=True)
    trade_no: Mapped[str | None]
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", values_callable=lambda e: [m.value for m in e]),
        default=OrderStatus.PENDING,
        server_default=OrderStatus.PENDING.value,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PaymentLog(Base):
    __tablename__ = "payment_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_no: Mapped[str] = mapped_column(unique=True, index=True)
    received_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

