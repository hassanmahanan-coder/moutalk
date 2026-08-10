"""场景包加载器：从 JSON 目录加载，支持校验与扩展。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SCENARIO_DIR = Path(__file__).parent


def load_scenario(scenario_id: str) -> dict:
    """按 id 加载场景包 JSON，如 it_procurement / salary / supplier。"""
    path = SCENARIO_DIR / f"{scenario_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"场景包不存在: {scenario_id}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    validate_scenario(data)
    return data


def validate_scenario(data: dict) -> None:
    """校验场景包必填字段，防止配置错误进入引擎。"""
    required = {"id", "title", "opening_line", "safe_fallback", "dimensions"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"场景包缺少字段: {missing}")
    for dim in data["dimensions"]:
        for key in ("key", "label", "direction", "bottom_line", "keywords"):
            if key not in dim:
                raise ValueError(f"维度缺少字段 {key}: {dim}")
        if dim["direction"] not in ("min", "max"):
            raise ValueError(f"维度 direction 非法: {dim['direction']}")


@lru_cache
def list_scenarios() -> list[str]:
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.json") if p.stem != "__init__")
