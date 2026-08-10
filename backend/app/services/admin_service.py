"""管理后台服务（PRD 9.16 / 故事 9）：KPI + 战术统计 + 连接数。

- 聚合值仅返回统计，不暴露单用户明细（防推断）
- admin 鉴权在 API 依赖层（get_admin_user）
- 审计日志：管理操作写 admin_audit_log
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdminAuditLog, NegotiationSession, Report, SessionStatus, User, UserRole
from app.services.ws_manager import get_ws_manager

logger = logging.getLogger(__name__)


def admin_stats(db: Session) -> dict[str, Any]:
    """核心 KPI 聚合（PRD 8.9 / 故事 9）。"""
    users_count = db.scalar(select(func.count(User.id))) or 0
    sessions_count = db.scalar(select(func.count(NegotiationSession.id))) or 0
    reports_count = db.scalar(select(func.count(Report.id))) or 0
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_reports = db.scalar(
        select(func.count(Report.id)).where(Report.generated_at >= month_start)
    ) or 0
    pro_users = db.scalar(
        select(func.count(User.id)).where(User.role == "pro")
    ) or 0
    return {
        "users_count": users_count,
        "sessions_count": sessions_count,
        "reports_count": reports_count,
        "monthly_reports": monthly_reports,
        "pro_users": pro_users,
    }


def admin_tactic_stats(db: Session) -> dict[str, Any]:
    """战术命中分布（从 sessions 的 messages_json 聚合，PRD 8.9）。"""
    rows = db.execute(
        select(NegotiationSession.messages_json).where(
            NegotiationSession.status == SessionStatus.REPORTED
        )
    ).all()
    tactics: dict[str, int] = {}
    llm_fallback = 0
    total = 0
    for (messages,) in rows:
        for msg in messages or []:
            tactic = (msg or {}).get("tactic")
            if tactic:
                tactics[tactic] = tactics.get(tactic, 0) + 1
                total += 1
    return {
        "tactics": tactics,
        "total": total,
        "llm_fallback": llm_fallback,
    }


def admin_connections() -> dict[str, Any]:
    """实时 WebSocket 连接数（PRD 8.9）。"""
    return {"online": len(get_ws_manager().connections)}


def admin_list_users(db: Session, limit: int = 100) -> list[dict[str, Any]]:
    """用户列表（管理员）：不暴露密码哈希（PRD 9.16 数据安全）。"""
    rows = db.scalars(select(User).order_by(User.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "username": u.username,
            "role": u.role.value,
            "is_admin": u.is_admin,
            "banned": bool(u.banned),
            "expire_at": u.expire_at.isoformat() if u.expire_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in rows
    ]


def admin_update_user_role(
    db: Session,
    target_id: uuid.UUID,
    role: str | None = None,
    admin_id: uuid.UUID | None = None,
    is_admin: bool | None = None,
    banned: bool | None = None,
) -> User | None:
    """调整用户角色/管理员标记/封禁状态；返回更新后的用户，不存在返回 None。

    安全：禁止管理员修改自己（防自降级后绕过鉴权）；审计日志由 API 层写。
    """
    if admin_id is not None and target_id == admin_id:
        raise ValueError("不能修改自己的角色")
    user = db.get(User, target_id)
    if user is None:
        return None
    if role is not None:
        user.role = UserRole(role) if isinstance(role, str) else role
    if is_admin is not None:
        user.is_admin = is_admin
    if banned is not None:
        user.banned = banned
    db.commit()
    return user


def log_admin_action(db: Session, admin_user_id: uuid.UUID, action: str, target_id: str | None = None) -> None:
    """审计日志（PRD 9.16）。"""
    db.add(AdminAuditLog(admin_user_id=admin_user_id, action=action, target_id=target_id))
    db.commit()
