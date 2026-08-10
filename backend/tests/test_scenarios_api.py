"""场景包 API 测试：列表 + 详情（故事 2：展示可用场景包列表）。"""

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.services.scenario_seed import seed_scenarios


@pytest.fixture
def client(session):
    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(session):
    seed_scenarios(session)
    session.commit()


def test_list_scenarios_public(client, seeded):
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    items = r.json()["items"]
    ids = [s["id"] for s in items]
    assert set(ids) == {"it_procurement", "salary", "supplier"}


def test_list_scenarios_fields(client, seeded):
    items = client.get("/api/scenarios").json()["items"]
    it = next(s for s in items if s["id"] == "it_procurement")
    assert it["title"] == "IT 采购谈判"
    assert it["domain"] == "it_procurement"
    assert it["difficulty"] == "medium"
    assert it["opponent_style"] == "专业严谨"
    assert it["briefing"]
    assert it["is_free"] is True


def test_get_scenario_detail(client, seeded):
    r = client.get("/api/scenarios/it_procurement")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "it_procurement"
    assert body["opening_line"]
    assert body["rules"]
    dims = body["dimensions"]
    assert len(dims) == 4
    assert dims[0]["key"] == "price"
    assert body["weights"]["price"] == 0.5


def test_get_scenario_404(client, seeded):
    r = client.get("/api/scenarios/nonexistent")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SCENARIO_NOT_FOUND"


def test_list_hides_off_sale_scenarios(client, seeded, session):
    """下架场景对用户不可见（管理后台上下架，PRD 9.16 扩展）。"""
    from sqlalchemy import select

    from app.models import Scenario

    sc = session.scalar(select(Scenario).where(Scenario.id == "salary"))
    sc.on_sale = False
    session.commit()
    items = client.get("/api/scenarios").json()["items"]
    ids = [s["id"] for s in items]
    assert "salary" not in ids
    assert "it_procurement" in ids


def test_get_off_sale_detail_404(client, seeded, session):
    from sqlalchemy import select

    from app.models import Scenario

    sc = session.scalar(select(Scenario).where(Scenario.id == "salary"))
    sc.on_sale = False
    session.commit()
    assert client.get("/api/scenarios/salary").status_code == 404
