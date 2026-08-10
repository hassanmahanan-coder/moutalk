import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.db import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, index=True
    )
    total_score: Mapped[Numeric | None] = mapped_column(Numeric(5, 2))
    objective_json: Mapped[dict | None] = mapped_column(JSON)
    subjective_json: Mapped[dict | None] = mapped_column(JSON)
    concession_curve: Mapped[list | None] = mapped_column(JSON)
    weak_points: Mapped[list | None] = mapped_column(JSON)
    advice: Mapped[str | None]
    pdf_url: Mapped[str | None]
    generated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
