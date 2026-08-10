"""管理后台 API（PRD 9.16 / 故事 9）：KPI + 战术统计 + 连接数。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user
from app.core.db import get_db
from app.models import User
from app.services import admin_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict:
    """核心 KPI（PRD 8.9）。"""
    return admin_service.admin_stats(db)


@router.get("/tactic-stats")
def tactic_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict:
    """战术命中分布（PRD 8.9 / 9.7 监控）。"""
    return admin_service.admin_tactic_stats(db)


@router.get("/connections")
def connections(
    admin: User = Depends(get_admin_user),
) -> dict:
    """实时 WebSocket 连接数（PRD 8.9）。"""
    return admin_service.admin_connections()
