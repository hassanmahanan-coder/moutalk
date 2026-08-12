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
    """按会话加载场景配置：DB 优先（自定义），官方 JSON 文件兜底。

    官方场景的 DB config_json 可能不完整（如测试/历史数据缺 dimensions），
    此时回退文件加载；自定义场景必含 dimensions（校验器强制），恒用 DB。
    """
    row = db.scalar(select(Scenario).where(Scenario.id == scenario_id))
    if row is not None and row.config_json:
        if row.config_json.get("dimensions"):
            return row.config_json
        # 官方场景且 DB 配置不完整：回退完整 JSON 文件
        if row.owner_id is None:
            return load_scenario(scenario_id)
        return row.config_json
    return load_scenario(scenario_id)
