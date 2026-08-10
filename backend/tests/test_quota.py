"""免费额度服务测试：Redis 原子计数（PRD 7.3 / 9.11）。"""

import uuid
from datetime import UTC, datetime

import pytest

from app.services.quota import FREE_LIMIT, UsageCounter, monthly_key, usage_key


@pytest.fixture
def counter():
    return UsageCounter(prefix="test_usage:")


def test_monthly_key_format():
    now = datetime.now(UTC)
    key = monthly_key("user-1", "it_procurement", now)
    assert key == f"usage:user-1:it_procurement:{now.strftime('%Y%m')}"


def test_check_and_increment_until_limit(counter):
    uid = str(uuid.uuid4())
    assert counter.check_and_increment(uid, "it_procurement") is True
    for _ in range(FREE_LIMIT - 1):
        assert counter.check_and_increment(uid, "it_procurement") is True
    assert counter.check_and_increment(uid, "it_procurement") is False


def test_quota_isolated_per_scenario(counter):
    uid = str(uuid.uuid4())
    for _ in range(FREE_LIMIT):
        counter.check_and_increment(uid, "it_procurement")
    assert counter.check_and_increment(uid, "salary") is True


def test_quota_isolated_per_user(counter):
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    for _ in range(FREE_LIMIT):
        counter.check_and_increment(a, "it_procurement")
    assert counter.check_and_increment(b, "it_procurement") is True


def test_current_usage(counter):
    uid = str(uuid.uuid4())
    assert counter.current_usage(uid, "it_procurement") == 0
    counter.check_and_increment(uid, "it_procurement")
    counter.check_and_increment(uid, "it_procurement")
    assert counter.current_usage(uid, "it_procurement") == 2


def test_usage_key_contains_prefix(counter, monkeypatch):
    monkeypatch.setattr(counter, "prefix", "test_usage:")
    uid = str(uuid.uuid4())
    key = usage_key(counter.prefix, uid, "it_procurement")
    assert key.startswith("test_usage:")
