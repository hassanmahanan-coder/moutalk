"""管理后台 API（PRD 9.16 / 故事 9）：KPI + 战术统计 + 连接数 + 用户管理。"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user
from app.core.db import get_db
from app.models import Scenario, User, UserRole
from app.services import admin_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UpdateUserRoleRequest(BaseModel):
    role: UserRole | None = None
    is_admin: bool | None = None


class UpdateScenarioRequest(BaseModel):
    price: float | None = None
    on_sale: bool | None = None


@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict:
    """核心 KPI（PRD 8.9）。"""
    admin_service.log_admin_action(db, admin.id, "view_stats")
    return admin_service.admin_stats(db)


@router.get("/tactic-stats")
def tactic_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict:
    """战术命中分布（PRD 8.9 / 9.7 监控）。"""
    admin_service.log_admin_action(db, admin.id, "view_tactic_stats")
    return admin_service.admin_tactic_stats(db)


@router.get("/connections")
def connections(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict:
    """实时 WebSocket 连接数（PRD 8.9）。"""
    admin_service.log_admin_action(db, admin.id, "view_connections")
    return admin_service.admin_connections()


@router.get("/users")
def list_users(
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict:
    """用户列表（管理员，PRD 9.16）：不含密码哈希。"""
    admin_service.log_admin_action(db, admin.id, "view_users")
    return {"items": admin_service.admin_list_users(db, limit=limit)}


@router.patch("/users/{user_id}")
def update_user_role(
    user_id: str,
    req: UpdateUserRoleRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict:
    """调整用户角色/管理员标记（管理员，PRD 9.16）：写审计日志。"""
    if req.role is None and req.is_admin is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "EMPTY_UPDATE", "message": "至少提供一个修改项"},
        )
    # 兼容 pydantic v1/v2 对 str-枚举的解析差异（v1 解析为 str，v2 为枚举）
    role_value = (
        req.role.value if isinstance(req.role, UserRole) else str(req.role) if req.role else None
    )
    try:
        target_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "用户不存在"},
        )
    try:
        user = admin_service.admin_update_user_role(
            db, target_id, role=role_value, admin_id=admin.id, is_admin=req.is_admin
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SELF_ROLE_CHANGE", "message": str(exc)},
        )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "用户不存在"},
        )
    admin_service.log_admin_action(db, admin.id, "update_user_role", target_id=str(user.id))
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "role": user.role.value,
        "is_admin": bool(user.is_admin),
    }


@router.get("/scenarios")
def list_scenarios(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict:
    """场景包管理列表（含上下架/价格，PRD 9.16 扩展）。"""
    admin_service.log_admin_action(db, admin.id, "view_scenarios")
    rows = db.scalars(select(Scenario).order_by(Scenario.id)).all()
    return {
        "items": [
            {
                "id": s.id,
                "title": s.title,
                "domain": s.domain.value,
                "price": float(s.price) if s.price is not None else None,
                "is_free": bool(s.is_free),
                "on_sale": bool(s.on_sale),
            }
            for s in rows
        ]
    }


@router.patch("/scenarios/{scenario_id}")
def update_scenario(
    scenario_id: str,
    req: UpdateScenarioRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict:
    """场景上下架/定价（管理员）：写审计日志。"""
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCENARIO_NOT_FOUND", "message": "场景包不存在"},
        )
    if req.price is not None:
        if req.price < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "INVALID_PRICE", "message": "价格不能为负"},
            )
        scenario.price = req.price
    if req.on_sale is not None:
        scenario.on_sale = req.on_sale
    db.commit()
    admin_service.log_admin_action(db, admin.id, "update_scenario", target_id=scenario.id)
    return {
        "id": scenario.id,
        "title": scenario.title,
        "price": float(scenario.price) if scenario.price is not None else None,
        "on_sale": bool(scenario.on_sale),
    }
