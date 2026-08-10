"""谈判回放服务（PRD 9.17 / 故事 10）：从 sessions 数据重建时间轴。

- messages_json 约定：偶数下标=用户发言，奇数下标=AI 回复（每轮 2 条）
- 防御：奇数长度末尾补空回复，不抛错
- 纯组装无额外存储；单场 <20 轮全量返回
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NegotiationSession, Scenario

logger = logging.getLogger(__name__)


class ReplayError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def build_replay(db: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
    """组装回放轨迹（PRD 8.8 / 9.17）。"""
    ns = db.get(NegotiationSession, session_id)
    if ns is None:
        raise ReplayError("SESSION_NOT_FOUND", "会话不存在")
    if ns.user_id != user_id:
        raise ReplayError("FORBIDDEN", "无权回放他人会话")

    scenario_row = db.scalar(select(Scenario.title).where(Scenario.id == ns.scenario_id))
    messages = list(ns.messages_json or [])
    offers = list(ns.offers_json or [])

    rounds: list[dict[str, Any]] = []
    total = (len(messages) + 1) // 2  # 每轮 2 条，向上取整
    for i in range(total):
        user_msg = messages[i * 2] if i * 2 < len(messages) else None
        ai_msg = messages[i * 2 + 1] if i * 2 + 1 < len(messages) else None
        rounds.append(
            {
                "round": i + 1,
                "user_text": (user_msg or {}).get("content", ""),
                "reply": (ai_msg or {}).get("content", ""),
                "tactic": (ai_msg or {}).get("tactic", ""),
                "offer": offers[i].get("numbers") if i < len(offers) else None,
                "bottom_line_status": (ai_msg or {}).get("bottom_line_status", ""),
            }
        )
    return {
        "rounds": rounds,
        "total_rounds": total,
        "scenario_title": scenario_row or ns.scenario_id,
    }
