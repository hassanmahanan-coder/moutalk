"""场景包加载（官方文件 / 自定义 DB 统一入口）。

- 官方场景：app/scenarios/*.json
- 自定义场景：scenarios 表 config_json（owner_id 归属）
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Scenario
from app.scenarios import load_scenario


def load_scenario_for_session(db: Session, scenario_id: str) -> dict:
    """按会话加载场景配置：DB 优先（自定义），否则官方 JSON 文件。"""
    row = db.scalar(select(Scenario).where(Scenario.id == scenario_id))
    if row is not None:
        return row.config_json or {}
    return load_scenario(scenario_id)
