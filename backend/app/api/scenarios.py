"""场景包 API：列表 + 详情（公开）+ 自定义场景（用户私有）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_user
from app.core.db import get_db
from app.models import Scenario, User
from app.services.scenario_validator import (
    ScenarioValidationError,
    generate_scenario_id,
    validate_custom_scenario,
)

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


class CustomScenarioRequest(BaseModel):
    config: dict = Field(..., description="完整场景配置（对齐官方场景包结构）")


def _summary(s: Scenario) -> dict:
    cfg = s.config_json or {}
    return {
        "id": s.id,
        "title": s.title,
        "domain": s.domain.value,
        "difficulty": cfg.get("difficulty", ""),
        "opponent_style": cfg.get("opponent_style", ""),
        "briefing": cfg.get("briefing", ""),
        "price": float(s.price) if s.price is not None else None,
        "is_free": bool(s.is_free),
        "is_custom": s.owner_id is not None,
    }


@router.get("")
def list_scenarios_api(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """官方在售场景（公开）+ 自己的自定义场景（登录后叠加）。"""
    query = select(Scenario).where(Scenario.on_sale.is_(True))
    if user is not None:
        query = query.where(or_(Scenario.owner_id.is_(None), Scenario.owner_id == user.id))
    else:
        query = query.where(Scenario.owner_id.is_(None))
    rows = db.scalars(query.order_by(Scenario.id)).all()
    return {"items": [_summary(s) for s in rows]}


@router.get("/{scenario_id}")
def get_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    query = select(Scenario).where(
        Scenario.id == scenario_id, Scenario.on_sale.is_(True)
    )
    if user is not None:
        query = query.where(or_(Scenario.owner_id.is_(None), Scenario.owner_id == user.id))
    else:
        query = query.where(Scenario.owner_id.is_(None))
    row = db.scalar(query)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCENARIO_NOT_FOUND", "message": "场景包不存在"},
        )
    from app.services.scenario_loader import load_scenario_for_session

    cfg = load_scenario_for_session(db, scenario_id)
    return {
        **_summary(row),
        "briefing": cfg.get("briefing", ""),
        "rules": cfg.get("rules", ""),
        "opponent_role": cfg.get("opponent_role", ""),
        "opening_line": cfg.get("opening_line", ""),
        "safe_fallback": cfg.get("safe_fallback", []),
        "dimensions": cfg.get("dimensions", []),
        "weights": cfg.get("weights", {}),
    }


@router.post("/custom", status_code=status.HTTP_201_CREATED)
def create_custom_scenario(
    req: CustomScenarioRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """创建自定义场景（用户私有，校验结构后入库）。"""
    try:
        cfg = validate_custom_scenario(req.config)
    except ScenarioValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "SCENARIO_INVALID", "message": str(exc)},
        )
    base_id = generate_scenario_id(cfg["title"])
    scenario_id = base_id
    suffix = 1
    while db.scalar(select(Scenario).where(Scenario.id == scenario_id)) is not None:
        scenario_id = f"{base_id}_{suffix}"
        suffix += 1
    scenario = Scenario(
        id=scenario_id,
        domain="it_procurement",
        title=cfg["title"],
        config_json=cfg,
        is_free=True,
        on_sale=True,
        owner_id=user.id,
    )
    db.add(scenario)
    db.commit()
    return {"id": scenario.id, "title": scenario.title, "is_custom": True}


@router.put("/custom/{scenario_id}")
def update_custom_scenario(
    scenario_id: str,
    req: CustomScenarioRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """修改自定义场景（归属校验 + 全量重新校验）。"""
    row = db.scalar(
        select(Scenario).where(
            Scenario.id == scenario_id, Scenario.owner_id == user.id
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "无权修改该场景"},
        )
    try:
        cfg = validate_custom_scenario(req.config)
    except ScenarioValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "SCENARIO_INVALID", "message": str(exc)},
        )
    row.title = cfg["title"]
    row.config_json = cfg
    db.commit()
    return {"id": row.id, "title": row.title, "is_custom": True}


@router.delete("/custom/{scenario_id}")
def delete_custom_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """删除自定义场景（归属校验；级联删除其会话，FK 为 RESTRICT）。"""
    row = db.scalar(
        select(Scenario).where(
            Scenario.id == scenario_id, Scenario.owner_id == user.id
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "无权删除该场景"},
        )
    from sqlalchemy import delete

    from app.models import NegotiationSession

    # FK sessions.scenario_id 为 RESTRICT：先级联删除该场景的全部会话
    db.execute(
        delete(NegotiationSession).where(NegotiationSession.scenario_id == scenario_id)
    )
    db.delete(row)
    db.commit()
    return {"deleted": True}
