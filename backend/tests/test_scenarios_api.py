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


# ---- 自定义场景（未来规划：用户自定义场景包工具）----


def _custom_payload() -> dict:
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


@pytest.fixture
def auth(client):
    client.post(
        "/api/auth/register",
        json={"username": "scenario_owner", "email": "sowner@example.com", "password": "password123"},
    )
    tok = client.post(
        "/api/auth/login",
        json={"account": "sowner@example.com", "password": "password123"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_create_custom_scenario(client, auth):
    r = client.post("/api/scenarios/custom", json={"config": _custom_payload()}, headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "办公室租赁谈判"
    assert body["id"].startswith("custom") or body["id"].startswith("office")


def test_create_custom_invalid_422(client, auth):
    payload = _custom_payload()
    payload["weights"] = {"rent": 1.0}
    r = client.post("/api/scenarios/custom", json={"config": payload}, headers=auth)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SCENARIO_INVALID"


def test_create_custom_requires_auth(client):
    assert client.post("/api/scenarios/custom", json={"config": _custom_payload()}).status_code == 401


def test_custom_scenario_visible_to_owner(client, auth):
    created = client.post("/api/scenarios/custom", json={"config": _custom_payload()}, headers=auth).json()
    items = client.get("/api/scenarios", headers=auth).json()["items"]
    ids = [s["id"] for s in items]
    assert created["id"] in ids, "拥有者可见自己的自定义场景"


def test_custom_scenario_hidden_from_others(client, auth):
    created = client.post("/api/scenarios/custom", json={"config": _custom_payload()}, headers=auth).json()
    client.post(
        "/api/auth/register",
        json={"username": "other_user", "email": "other_s@example.com", "password": "password123"},
    )
    tok = client.post(
        "/api/auth/login",
        json={"account": "other_s@example.com", "password": "password123"},
    ).json()["access_token"]
    items = client.get(
        "/api/scenarios", headers={"Authorization": f"Bearer {tok}"}
    ).json()["items"]
    assert created["id"] not in [s["id"] for s in items], "他人不可见我的自定义场景"


def test_delete_custom_scenario(client, auth, session):
    created = client.post("/api/scenarios/custom", json={"config": _custom_payload()}, headers=auth).json()
    r = client.delete(f"/api/scenarios/custom/{created['id']}", headers=auth)
    assert r.status_code == 200
    assert client.get(f"/api/scenarios/{created['id']}", headers=auth).status_code == 404


def test_delete_custom_scenario_other_user_403(client, auth):
    created = client.post("/api/scenarios/custom", json={"config": _custom_payload()}, headers=auth).json()
    client.post(
        "/api/auth/register",
        json={"username": "other_del", "email": "other_del@example.com", "password": "password123"},
    )
    tok = client.post(
        "/api/auth/login",
        json={"account": "other_del@example.com", "password": "password123"},
    ).json()["access_token"]
    r = client.delete(
        f"/api/scenarios/custom/{created['id']}",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403


def test_custom_scenario_can_start_session(client, auth, session):
    created = client.post("/api/scenarios/custom", json={"config": _custom_payload()}, headers=auth).json()
    r = client.post(
        "/api/sessions",
        json={"scenario_id": created["id"]},
        headers=auth,
    )
    assert r.status_code == 201, r.text


def test_delete_custom_scenario_with_sessions(client, auth, session):
    """有会话引用时仍可删除（级联清理会话，FK RESTRICT）。"""
    created = client.post("/api/scenarios/custom", json={"config": _custom_payload()}, headers=auth).json()
    client.post("/api/sessions", json={"scenario_id": created["id"]}, headers=auth)
    r = client.delete(f"/api/scenarios/custom/{created['id']}", headers=auth)
    assert r.status_code == 200
    assert client.get(f"/api/scenarios/{created['id']}", headers=auth).status_code == 404


def test_custom_scenario_report_generation(client, auth, session):
    """自定义场景谈判结束后报告必须能生成（报告服务场景加载兼容，C.9）。"""
    import asyncio

    from sqlalchemy import select

    from app.engine.engine import NegotiationEngine
    from app.engine.llm import MockLLM
    from app.models import NegotiationSession, User
    from app.services.report_service import generate_report
    from app.services.scenario_loader import load_scenario_for_session
    from app.services.session_store import save_round

    created = client.post("/api/scenarios/custom", json={"config": _custom_payload()}, headers=auth).json()
    owner = session.scalar(select(User).where(User.email == "sowner@example.com"))
    ns = NegotiationSession(user_id=owner.id, scenario_id=created["id"])
    session.add(ns)
    session.commit()

    eng = NegotiationEngine(load_scenario_for_session(session, created["id"]), llm=MockLLM())
    state = eng.initial_state(str(ns.id))
    state = asyncio.run(eng.run_round(state, "租金太贵了，2.5 万可以吗？"))
    save_round(session, ns.id, state)
    session.commit()

    report = asyncio.run(generate_report(session, ns.id))
    assert report.total_score is not None
    assert report.session_id == ns.id
    assert report.objective_json["dimensions"]["price_attainment"] is not None


def test_other_user_cannot_start_custom_session(client, auth):
    created = client.post("/api/scenarios/custom", json={"config": _custom_payload()}, headers=auth).json()
    client.post(
        "/api/auth/register",
        json={"username": "other_ses", "email": "other_ses@example.com", "password": "password123"},
    )
    tok = client.post(
        "/api/auth/login",
        json={"account": "other_ses@example.com", "password": "password123"},
    ).json()["access_token"]
    r = client.post(
        "/api/sessions",
        json={"scenario_id": created["id"]},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403
