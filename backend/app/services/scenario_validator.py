"""自定义场景校验（未来规划：用户自定义场景包工具）。

结构要求（对齐官方场景包）：
- 必填：title / briefing / rules / opponent_role / opening_line /
  safe_fallback(>=1) / dimensions(>=1) / weights
- 维度字段：key/label/direction(min|max)/first_offer/bottom_line/keywords(>=1)
- weights 必须覆盖全部维度 key 且总和 ≈ 1
"""

from __future__ import annotations

import re

_SLUG_RE = re.compile(r"^[a-z0-9_]{3,32}$")
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_DIMENSION_KEYS = {"key", "label", "direction", "first_offer", "bottom_line", "keywords"}


class ScenarioValidationError(Exception):
    pass


def validate_custom_scenario(data: dict) -> dict:
    """校验并规范化自定义场景配置；非法抛 ScenarioValidationError。"""
    if not isinstance(data, dict):
        raise ScenarioValidationError("场景配置必须是 JSON 对象")
    for field in ("title", "briefing", "rules", "opponent_role", "opening_line"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ScenarioValidationError(f"缺少必填字段: {field}")
    fallback = data.get("safe_fallback") or []
    if not isinstance(fallback, list) or not fallback or not all(
        isinstance(f, str) and f.strip() for f in fallback
    ):
        raise ScenarioValidationError("safe_fallback 至少需要 1 条安全话术")
    dims = data.get("dimensions") or []
    if not isinstance(dims, list) or not dims:
        raise ScenarioValidationError("dimensions 至少需要 1 个维度")
    dim_keys: list[str] = []
    for dim in dims:
        if not isinstance(dim, dict):
            raise ScenarioValidationError("维度必须是对象")
        key = dim.get("key")
        if not isinstance(key, str) or not _KEY_RE.match(key):
            raise ScenarioValidationError("维度 key 需为小写字母/数字/下划线（字母开头）")
        if key in dim_keys:
            raise ScenarioValidationError(f"维度 key 重复: {key}")
        dim_keys.append(key)
        if not isinstance(dim.get("label"), str) or not dim["label"].strip():
            raise ScenarioValidationError(f"维度 {key} 缺少 label")
        if dim.get("direction") not in ("min", "max"):
            raise ScenarioValidationError(f"维度 {key} 的 direction 需为 min/max")
        for num_field in ("first_offer", "bottom_line"):
            value = dim.get(num_field)
            if not isinstance(value, (int, float)) or value <= 0:
                raise ScenarioValidationError(f"维度 {key} 的 {num_field} 需为正数")
        kw = dim.get("keywords") or []
        if not isinstance(kw, list) or not kw or not all(isinstance(k, str) and k for k in kw):
            raise ScenarioValidationError(f"维度 {key} 至少需要 1 个关键词")
    weights = data.get("weights") or {}
    if not isinstance(weights, dict) or set(weights) != set(dim_keys):
        raise ScenarioValidationError("weights 必须覆盖全部维度且不含多余 key")
    total = sum(float(w) for w in weights.values())
    if not 0.99 <= total <= 1.01:
        raise ScenarioValidationError(f"weights 总和需为 1（当前 {total:.2f}）")
    return {
        "title": data["title"].strip(),
        "briefing": data["briefing"].strip(),
        "rules": data["rules"].strip(),
        "opponent_role": data["opponent_role"].strip(),
        "opening_line": data["opening_line"].strip(),
        "safe_fallback": [f.strip() for f in fallback],
        "dimensions": dims,
        "weights": {k: float(v) for k, v in weights.items()},
    }


def generate_scenario_id(title: str) -> str:
    """从标题生成 slug；与现有 id 冲突时追加随机后缀（由调用方保证唯一）。"""
    base = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "custom"
    return base[:32]
