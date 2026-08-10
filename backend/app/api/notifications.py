"""离线通知 API（PRD 9.15 / 故事 7）：未读拉取 + 已读标记 + 列表。"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import User
from app.services import notification_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    unread: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """拉取通知列表（unread=true 仅未读，PRD 7.6）。"""
    items = notification_service.list_notifications(db, current_user.id, unread_only=unread)
    return {"items": items}


@router.patch("/{notification_id}")
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """标记已读（归属校验，幂等）。"""
    try:
        nid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "NOTIFICATION_NOT_FOUND", "message": "通知不存在"})
    ok = notification_service.mark_read(db, nid, current_user.id)
    if not ok:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "无权操作该通知"})
    return {"read": True}
