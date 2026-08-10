import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.db import Base


class NotificationType(str, enum.Enum):
    REPORT = "report"
    PAYMENT = "payment"
    SYSTEM = "system"


class Notification(Base):
    """离线通知（PRD 9.15 / 故事 7）：报告就绪/支付成功/系统公告。

    双写策略：事件发生无论在线与否都落库；在线额外 WS 推送。
    (user_id, type, payload_hash) 唯一索引防同一事件重复落库（9.15 幂等）。
    """

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "type", "payload_hash", name="uq_notification_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[NotificationType] = mapped_column(
        Enum(
            NotificationType,
            name="notification_type",
            values_callable=lambda e: [m.value for m in e],
        ),
    )
    title: Mapped[str] = mapped_column(String(128))
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
