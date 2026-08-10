"""个人中心 API（PRD 7.7 / 故事 6）：额度看板 + 用户信息。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import User
from app.services.quota import quota_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quota", tags=["quota"])


@router.get("/me")
def get_my_quota(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """个人中心额度看板（PRD 7.7）：角色 + 各场景已用/剩余 + 订阅到期。"""
    summary = quota_summary(db, current_user.id, current_user.role.value)
    summary["expire_at"] = current_user.expire_at.isoformat() if current_user.expire_at else None
    return summary
