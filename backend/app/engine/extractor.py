"""数值提取器：从中文谈判话术中鲁棒提取价格/百分比/折扣（PRD 9.3）。

设计：
- 直取数字 + 单位（万/万元/块/元）
- 中文数字转阿拉伯（两百三十万 -> 230 万，一百七 -> 170，一万五 -> 15000）
- 百分比：5 个点 / 5% / 降价 5
- 折扣：9 折 -> 0.9
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CN_DIGITS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
CN_SECTIONS = {"十": 10, "百": 100, "千": 1000}
CN_BIG = {"万": 10_000, "亿": 100_000_000}
CN_ALL = "".join(CN_DIGITS) + "".join(CN_SECTIONS) + "".join(CN_BIG)
CN_REQUIRED = "零一二两三四五六七八九十"  # 不含 万/亿/千/百，避免孤立的"万"被命中

PRICE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(万元|万|块钱|元|块|￥)?")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:个点|个百分点|%)")
DISCOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*折")
CN_NUM_RE = re.compile(f"([{CN_ALL}]+)(?:\\s*元)?(?:\\s*(万元|万|块|元))?")


@dataclass
class Number:
    raw: str
    value: float
    unit_type: str  # price_wan / percent / discount / plain

    def __repr__(self) -> str:
        return f"Number({self.raw} = {self.value} {self.unit_type})"


def parse_cn_number(text: str) -> float | None:
    """中文数字字符串转数值（元）。

    支持口语省略：'一百七' -> 170，'三千五' -> 3500，'一万五' -> 15000。
    """
    if not text:
        return None
    total = 0.0
    section = 0.0
    digit = 0
    last_unit: str | None = None
    seen = False
    for ch in text:
        if ch in CN_DIGITS:
            digit = CN_DIGITS[ch]
            seen = True
        elif ch in CN_SECTIONS:
            if digit == 0:
                digit = 1
            section += digit * CN_SECTIONS[ch]
            digit = 0
            seen = True
            last_unit = ch
        elif ch in CN_BIG:
            if digit == 0 and section == 0:
                digit = 1
            section += digit
            seen = True
            total += section * CN_BIG[ch]
            section = 0.0
            digit = 0
            last_unit = ch
    if digit:
        if last_unit in CN_SECTIONS:
            digit *= CN_SECTIONS[last_unit] // 10  # 一百七=170, 三千五=3500
        elif last_unit in CN_BIG:
            digit *= CN_BIG[last_unit] // 10  # 一万五=15000
        section += digit
    value = total + section
    if not seen:
        return None
    return value if value > 0 else 0.0


def _cn_text_is_valid(g1: str) -> bool:
    """中文数字串必须含数字位（零一二…九十），排除孤立'万'/'亿'。"""
    return any(ch in CN_REQUIRED for ch in g1)


def _to_wan(value: float, unit: str) -> float:
    if unit in ("元", "块", "块钱", "￥"):
        return value / 10_000
    return value  # 万/万元 或空：值本身即万元口径（数字直取）


def extract_numbers(text: str) -> list[Number]:
    """从话术中提取全部数值。价格统一为万元口径。"""
    if not text:
        return []
    out: list[Number] = []
    for m in DISCOUNT_RE.finditer(text):
        out.append(Number(m.group(0), round(float(m.group(1)) / 10, 4), "discount"))
    for m in PERCENT_RE.finditer(text):
        out.append(Number(m.group(0), float(m.group(1)), "percent"))
    for m in PRICE_RE.finditer(text):
        raw = m.group(0)
        if any(n.raw == raw for n in out):
            continue
        val = _to_wan(float(m.group(1)), m.group(2) or "")
        unit_type = "price_wan" if m.group(2) else "plain"
        out.append(Number(raw, val, unit_type))
    for m in CN_NUM_RE.finditer(text):
        raw = m.group(0)
        g1 = m.group(1)
        if not _cn_text_is_valid(g1) or any(n.raw == raw for n in out):
            continue
        base = parse_cn_number(g1)
        if base is None:
            continue
        has_big_unit = "万" in g1 or "亿" in g1
        if has_big_unit or m.group(2) in ("万", "万元"):
            # 中文数字算出的 base 是元，统一换算为万元
            out.append(Number(raw, round(base / 10_000, 4), "price_wan"))
        else:
            out.append(Number(raw, base, "plain"))
    return out


def first_price(text: str) -> float | None:
    """取话术中第一个价格（万元），用于底线比对；无则 None。"""
    nums = extract_numbers(text)
    for n in nums:
        if n.unit_type == "price_wan":
            return n.value
    for n in nums:
        if n.unit_type == "plain":
            return n.value
    return None
