import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.db import Base


class UserRole(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    username: Mapped[str | None] = mapped_column(
        unique=True, index=True, nullable=True
    )  # 账号登录用户名（3-20 位小写字母/数字/下划线；老用户为空）
    password_hash: Mapped[str]
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        default=UserRole.FREE,
        server_default=UserRole.FREE.value,
    )
    expire_at: Mapped[datetime | None]
    is_admin: Mapped[bool] = mapped_column(default=False, server_default="false")  # PRD 9.16
    banned: Mapped[bool] = mapped_column(default=False, server_default="false")  # 管理后台封禁
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

