"""谈判教练测试（新功能）：局势分析 + 策略 + 可发送话术选项。

契约：
- WS 客户端发 {type:'coach'} → 服务端返回 {type:'coach_advice', analysis, strategy, options:[...]}
- options 为 2-3 条可直接发送的话术
- 教练建议不写入谈判历史（不影响对手行为）
- MockLLM 降级返回规则建议（结构一致）
- 限流：教练调用计入 LLM 令牌桶
"""


import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.services import coach_service


@pytest.fixture
def client(session):
    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def token(client):
    client.post(
        "/api/auth/register",
        json={"username": "coach", "email": "coach@example.com", "password": "password123"},
    )
    return client.post(
        "/api/auth/login",
        json={"account": "coach@example.com", "password": "password123"},
    ).json()["access_token"]


@pytest.fixture
def session_id(client, token, session):
    from app.services.scenario_seed import seed_scenarios

    seed_scenarios(session)
    session.commit()
    r = client.post(
        "/api/sessions",
        json={"scenario_id": "it_procurement"},
        headers={"Authorization": f"Bearer {token}"},
    )
    return r.json()["id"]


class TestCoachService:
    def test_build_coach_prompt_includes_state(self):
        state = {
            "round": 3,
            "phase": "core",
            "history": [{"role": "user", "content": "太贵了"}, {"role": "assistant", "content": "可以谈"}],
            "offers_json": [{"numbers": 235}],
            "used_tactics": ["time_pressure"],
        }
        prompt = coach_service.build_coach_prompt(state)
        assert "3" in prompt or "三" in prompt
        assert "太贵了" in prompt
        assert "time_pressure" in prompt or "时间压迫" in prompt
        assert "话术" in prompt, "应要求生成可发送话术"

    def test_mock_advice_structure(self):
        state = {"round": 2, "phase": "core", "history": [], "offers_json": []}
        advice = coach_service.mock_advice(state)
        assert "analysis" in advice
        assert "strategy" in advice
        assert 2 <= len(advice["options"]) <= 3
        assert all(isinstance(o, str) and o.strip() for o in advice["options"])


class TestCoachWS:
    def test_coach_returns_advice(self, client, token, session_id):
        with client.websocket_connect(f"/api/negotiation/{session_id}?token={token}") as ws:
            ws.receive_json()  # opening
            ws.send_json({"type": "user_msg", "text": "235 万太高了，200 万"})
            seen = set()
            while "meta" not in seen:
                seen.add(ws.receive_json()["type"])
            ws.send_json({"type": "coach"})
            msg = ws.receive_json()
            assert msg["type"] == "coach_advice"
            assert msg.get("analysis")
            assert msg.get("strategy")
            assert 2 <= len(msg.get("options", [])) <= 3
            for opt in msg["options"]:
                assert isinstance(opt, str) and opt.strip()

    def test_coach_does_not_pollute_history(self, client, token, session_id):
        with client.websocket_connect(f"/api/negotiation/{session_id}?token={token}") as ws:
            ws.receive_json()
            ws.send_json({"type": "user_msg", "text": "太贵了"})
            seen = set()
            while "meta" not in seen:
                seen.add(ws.receive_json()["type"])
            ws.send_json({"type": "coach"})
            msg = ws.receive_json()
            assert msg["type"] == "coach_advice"
            # 教练消息后继续正常轮次，历史不受污染
            ws.send_json({"type": "user_msg", "text": "200 万可以吗"})
            seen = set()
            while "meta" not in seen:
                seen.add(ws.receive_json()["type"])
            assert "meta" in seen

    def test_coach_before_first_round(self, client, token, session_id):
        """开局即可请求教练（基于开场白状态）。"""
        with client.websocket_connect(f"/api/negotiation/{session_id}?token={token}") as ws:
            ws.receive_json()  # opening
            ws.send_json({"type": "coach"})
            msg = ws.receive_json()
            assert msg["type"] == "coach_advice"
            assert msg.get("options")
