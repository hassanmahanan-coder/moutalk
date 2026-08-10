"""数值提取器测试：覆盖 PRD 9.3 数值表达样例（直接数字/中文数字/百分比/折扣/隐含）。"""

import pytest

from app.engine.extractor import extract_numbers, first_price, parse_cn_number


class TestCnNumber:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("两百三十", 230),
            ("一百七", 170),
            ("两百万", 2_000_000),
            ("三千五百", 3500),
            ("九", 9),
            ("十", 10),
            ("十五", 15),
            ("零", 0),
            ("", None),
            ("abc", None),
        ],
    )
    def test_parse_cn_number(self, text: str, expected: float | None):
        assert parse_cn_number(text) == expected


class TestExtractNumbers:
    @pytest.mark.parametrize(
        "text,expect_price_wan",
        [
            ("235 万", [235.0]),
            ("170 万元", [170.0]),
            ("报价：两百三十万", [230.0]),
            ("一口价 180 万", [180.0]),
            ("报价 3000 元", [0.3]),
        ],
    )
    def test_price(self, text: str, expect_price_wan: list[float]):
        vals = [n.value for n in extract_numbers(text) if n.unit_type == "price_wan"]
        assert vals == expect_price_wan

    @pytest.mark.parametrize(
        "text,expect_percent",
        [
            ("降价 5 个点", [5.0]),
            ("再降 3 个百分点", [3.0]),
            ("优惠 8%", [8.0]),
        ],
    )
    def test_percent(self, text: str, expect_percent: list[float]):
        vals = [n.value for n in extract_numbers(text) if n.unit_type == "percent"]
        assert vals == expect_percent

    def test_discount(self):
        vals = [n.value for n in extract_numbers("打 9 折") if n.unit_type == "discount"]
        assert vals == [0.9]

    def test_plain_number(self):
        vals = [n.value for n in extract_numbers("再减 20") if n.unit_type == "plain"]
        assert vals == [20.0]

    def test_mixed_sentence(self):
        ns = extract_numbers("贵方报价 235 万，若现款支付可降 2 个点，再打 9 折如何？")
        types = {(n.value, n.unit_type) for n in ns}
        assert (235.0, "price_wan") in types
        assert (2.0, "percent") in types
        assert (0.9, "discount") in types


class TestFirstPrice:
    def test_wan_preferred(self):
        assert first_price("首轮报价 235 万，单价再减 20") == 235.0

    def test_plain_fallback(self):
        assert first_price("再减 20 的话可以接受") == 20.0

    def test_none(self):
        assert first_price("您好，我们聊聊价格吧") is None
