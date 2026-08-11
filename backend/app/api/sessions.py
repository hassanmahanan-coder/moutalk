"""谈判会话 API：创建会话、历史列表、谈判回放（PRD 9.17）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import Scenario, User, UserRole
from app.services.quota import UsageCounter
from app.services.replay_service import ReplayError, build_replay
from app.services.session_store import create_session, list_sessions

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

usage_counter = UsageCounter()


class CreateSessionRequest(BaseModel):
    scenario_id: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create(req: CreateSessionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    scenario_row = db.scalar(select(Scenario).where(Scenario.id == req.scenario_id))
    if scenario_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCENARIO_NOT_FOUND", "message": "场景包不存在"},
        )
    if scenario_row.owner_id is not None and scenario_row.owner_id != user.id:
        # 自定义场景归属校验：他人私有场景不可开
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "无权使用该自定义场景"},
        )
    if user.role == UserRole.FREE and not usage_counter.check_and_increment(
        str(user.id), req.scenario_id
    ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FREE_QUOTA_EXCEEDED",
                    "message": "本月免费额度已用完，请升级 Pro 或购买场景包",
                },
            )
    ns = create_session(db, user.id, req.scenario_id)
    db.commit()
    from app.services.scenario_loader import load_scenario_for_session

    scenario = load_scenario_for_session(db, req.scenario_id)
    return {
        "id": str(ns.id),
        "scenario_id": req.scenario_id,
        "status": ns.status.value,
        "opening_line": scenario.get("opening_line", ""),
    }


@router.get("")
def list_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"sessions": list_sessions(db, user.id)}


@router.get("/{session_id}/replay")
def replay(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """谈判回放（PRD 9.17 / 故事 10）：重建时间轴，归属校验。"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": "会话不存在"})
    try:
        return build_replay(db, sid, user.id)
    except ReplayError as exc:
        code = 403 if exc.code == "FORBIDDEN" else 404
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message})
