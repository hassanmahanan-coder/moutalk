import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.db import Base


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    ENDED = "ended"
    REPORTED = "reported"


class NegotiationSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status", values_callable=lambda e: [m.value for m in e]),
        default=SessionStatus.ACTIVE,
        server_default=SessionStatus.ACTIVE.value,
    )
    messages_json: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    offers_json: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    simple_result: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

