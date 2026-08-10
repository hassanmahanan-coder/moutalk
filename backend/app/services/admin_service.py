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

from app.models import AdminAuditLog, NegotiationSession, Report, SessionStatus, User
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


def log_admin_action(db: Session, admin_user_id: uuid.UUID, action: str, target_id: str | None = None) -> None:
    """审计日志（PRD 9.16）。"""
    db.add(AdminAuditLog(admin_user_id=admin_user_id, action=action, target_id=target_id))
    db.commit()
