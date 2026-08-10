import enum
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.db import Base


class ScenarioDomain(str, enum.Enum):
    IT_PROCUREMENT = "it_procurement"
    SALARY = "salary"
    SUPPLIER = "supplier"


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain: Mapped[ScenarioDomain] = mapped_column(
        Enum(ScenarioDomain, name="scenario_domain", values_callable=lambda e: [m.value for m in e]),
        index=True,
    )
    title: Mapped[str]
    config_json: Mapped[dict] = mapped_column(JSON)
    price: Mapped[Numeric | None] = mapped_column(Numeric(10, 2))
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class UserScenarioAccess(Base):
    __tablename__ = "user_scenario_access"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True
    )
    purchased_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
