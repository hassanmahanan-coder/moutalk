"""场景包 API：列表 + 详情（公开，前端大厅展示）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Scenario
from app.scenarios import load_scenario

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


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
    }


@router.get("")
def list_scenarios_api(db: Session = Depends(get_db)) -> dict:
    # 仅展示在售场景（管理后台下架后用户端不可见）
    rows = db.scalars(
        select(Scenario).where(Scenario.on_sale.is_(True)).order_by(Scenario.id)
    ).all()
    return {"items": [_summary(s) for s in rows]}


@router.get("/{scenario_id}")
def get_scenario(scenario_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.scalar(
        select(Scenario).where(
            Scenario.id == scenario_id, Scenario.on_sale.is_(True)
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCENARIO_NOT_FOUND", "message": "场景包不存在"},
        )
    cfg = load_scenario(scenario_id)
    return {
        **_summary(row),
        "briefing": cfg.get("briefing", ""),
        "rules": cfg.get("rules", ""),
        "opponent_role": cfg.get("opponent_role", ""),
        "opening_line": cfg.get("opening_line", ""),
        "dimensions": cfg.get("dimensions", []),
        "weights": cfg.get("weights", {}),
    }
