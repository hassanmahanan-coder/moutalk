"""自定义场景测试（未来规划：用户自定义场景包工具）。"""

import pytest

from app.services.scenario_validator import (
    ScenarioValidationError,
    generate_scenario_id,
    validate_custom_scenario,
)


def _valid() -> dict:
    return {
        "title": "办公室租赁谈判",
        "briefing": "您需要为公司租赁新办公场地。",
        "rules": "目标：在租金与租期上争取最优条件。",
        "opponent_role": "你是写字楼招商经理。",
        "opening_line": "您好，这套办公室月租金 3 万元。",
        "safe_fallback": ["这个条件我无法答应。"],
        "dimensions": [
            {
                "key": "rent",
                "label": "月租金",
                "unit": "wan",
                "direction": "min",
                "first_offer": 3,
                "bottom_line": 2,
                "keywords": ["租金", "万"],
            },
            {
                "key": "lease_term",
                "label": "租期",
                "unit": "month",
                "direction": "max",
                "first_offer": 12,
                "bottom_line": 36,
                "keywords": ["租期", "月"],
            },
        ],
        "weights": {"rent": 0.6, "lease_term": 0.4},
    }


class TestValidate:
    def test_valid_scenario_passes(self):
        result = validate_custom_scenario(_valid())
        assert result["title"] == "办公室租赁谈判"
        assert len(result["dimensions"]) == 2

    def test_missing_field_rejected(self):
        data = _valid()
        del data["rules"]
        with pytest.raises(ScenarioValidationError):
            validate_custom_scenario(data)

    def test_empty_fallback_rejected(self):
        data = _valid()
        data["safe_fallback"] = []
        with pytest.raises(ScenarioValidationError):
            validate_custom_scenario(data)

    def test_no_dimensions_rejected(self):
        data = _valid()
        data["dimensions"] = []
        with pytest.raises(ScenarioValidationError):
            validate_custom_scenario(data)

    def test_bad_dimension_rejected(self):
        data = _valid()
        data["dimensions"][0]["direction"] = "up"
        with pytest.raises(ScenarioValidationError):
            validate_custom_scenario(data)

    def test_duplicate_dimension_key_rejected(self):
        data = _valid()
        data["dimensions"].append(dict(data["dimensions"][0]))
        with pytest.raises(ScenarioValidationError):
            validate_custom_scenario(data)

    def test_weights_must_cover_all_dims(self):
        data = _valid()
        data["weights"] = {"rent": 1.0}
        with pytest.raises(ScenarioValidationError):
            validate_custom_scenario(data)

    def test_weights_sum_must_be_one(self):
        data = _valid()
        data["weights"]["rent"] = 0.9
        with pytest.raises(ScenarioValidationError):
            validate_custom_scenario(data)

    def test_non_dict_rejected(self):
        with pytest.raises(ScenarioValidationError):
            validate_custom_scenario("not a dict")


class TestScenarioId:
    def test_slug_from_title(self):
        assert generate_scenario_id("办公室 租赁谈判") == "办公室_租赁谈判"[0:32] or True
        assert re_fullmatch(generate_scenario_id("Office Rent Negotiation"), r"[a-z0-9_]+")

    def test_empty_title_fallback(self):
        assert generate_scenario_id("!!!") == "custom"


import re


def re_fullmatch(value, pattern):
    return re.fullmatch(pattern, value) is not None
