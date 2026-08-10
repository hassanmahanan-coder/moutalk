"""谈判会话持久化：创建 / 保存轮次 / 结束 / 恢复状态（sessions 表 ↔ 引擎）。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NegotiationSession, Scenario, SessionStatus

logger = logging.getLogger(__name__)


class SessionNotFoundError(Exception):
    """会话不存在。"""


def create_session(db: Session, user_id: uuid.UUID, scenario_id: str) -> NegotiationSession:
    ns = NegotiationSession(user_id=user_id, scenario_id=scenario_id)
    db.add(ns)
    db.flush()
    return ns


def _get(db: Session, session_id: uuid.UUID) -> NegotiationSession:
    ns = db.scalar(
        select(NegotiationSession).where(NegotiationSession.id == session_id)
    )
    if ns is None:
        raise SessionNotFoundError(f"会话不存在: {session_id}")
    return ns


def save_round(db: Session, session_id: uuid.UUID, state: dict[str, Any]) -> None:
    """保存一轮谈判后的状态：完整历史、报价记录、简版结果。"""
    ns = _get(db, session_id)
    ns.messages_json = list(state.get("history") or [])
    ns.offers_json = list(state.get("offers_json") or [])
    if state.get("last_offer"):
        ns.simple_result = state.get("simple_result")


def end_session(
    db: Session, session_id: uuid.UUID, simple_result: dict[str, Any] | None = None
) -> None:
    """结束会话：状态置 ended，记录结束时间与简版结果。"""
    ns = _get(db, session_id)
    from datetime import UTC, datetime

    ns.status = SessionStatus.ENDED
    ns.ended_at = datetime.now(UTC)
    if simple_result is not None:
        ns.simple_result = simple_result


def get_session_state(db: Session, session_id: uuid.UUID) -> dict[str, Any]:
    """从 DB 恢复引擎可用的初始状态（断线重连 / 续谈）。"""
    ns = _get(db, session_id)
    scenario = db.scalar(
        select(Scenario).where(Scenario.id == ns.scenario_id)
    )
    if scenario is None:
        raise ValueError(f"会话关联的场景包不存在: {ns.scenario_id}")
    offers = list(ns.offers_json or [])
    history = list(ns.messages_json or [])
    rounds = sum(1 for m in history if m.get("role") == "assistant") + 1
    return {
        "id": str(ns.id),
        "session_id": str(ns.id),
        "round": rounds,
        "scenario_id": ns.scenario_id,
        "scenario": scenario.config_json,
        "history": list(ns.messages_json or []),
        "offers_json": offers,
        "last_offer": offers[-1] if offers else None,
    }


def list_sessions(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    """用户的历史会话摘要（按开始时间倒序）。"""
    rows = db.execute(
        select(NegotiationSession, Scenario.title, Scenario.domain)
        .join(Scenario, NegotiationSession.scenario_id == Scenario.id)
        .where(NegotiationSession.user_id == user_id)
        .order_by(NegotiationSession.started_at.desc())
    ).all()
    return [
        {
            "id": str(ns.id),
            "scenario_id": ns.scenario_id,
            "scenario_title": title,
            "domain": domain.value,
            "status": ns.status.value,
            "started_at": ns.started_at.isoformat() if ns.started_at else None,
            "ended_at": ns.ended_at.isoformat() if ns.ended_at else None,
            "simple_result": ns.simple_result,
        }
        for ns, title, domain in rows
    ]
