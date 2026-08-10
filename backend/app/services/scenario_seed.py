"""场景包种子数据：将 JSON 配置导入 scenarios 表（幂等）。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Scenario, ScenarioDomain
from app.scenarios import list_scenarios, load_scenario

logger = logging.getLogger(__name__)

_DOMAIN_MAP = {
    "it_procurement": ScenarioDomain.IT_PROCUREMENT,
    "salary": ScenarioDomain.SALARY,
    "supplier": ScenarioDomain.SUPPLIER,
}


def _to_model(scenario_id: str, data: dict[str, Any]) -> Scenario:
    return Scenario(
        id=data["id"],
        domain=_DOMAIN_MAP.get(data.get("domain", scenario_id), ScenarioDomain.IT_PROCUREMENT),
        title=data["title"],
        config_json=data,
        price=None,
        is_free=True,
    )


def seed_scenarios(db: Session) -> list[Scenario]:
    """导入全部场景包 JSON，已存在的跳过。返回新创建的记录列表。"""
    existing_ids = set(db.scalars(select(Scenario.id)).all())
    created: list[Scenario] = []
    for scenario_id in list_scenarios():
        if scenario_id in existing_ids:
            continue
        data = load_scenario(scenario_id)
        model = _to_model(scenario_id, data)
        db.add(model)
        created.append(model)
        logger.info("场景包入库: %s (%s)", data["id"], data["title"])
    return created
