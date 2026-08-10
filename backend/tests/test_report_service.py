"""复盘报告服务测试：简版结果、客观分规则引擎、报告生成与持久化（PRD 7.4 / 8.4 / 9.9）。"""

import uuid

import pytest
from sqlalchemy import select

from app.models import NegotiationSession, Report, SessionStatus
from app.services.report_service import (
    compute_objective_score,
    compute_simple_result,
    generate_report,
    get_report,
    list_reports,
)

SCENARIO = {
    "id": "it_procurement",
    "dimensions": [
        {
            "key": "price",
            "first_offer": 235,
            "bottom_line": 180,
            "direction": "min",
        }
    ],
}


def _prices(*values: float) -> list[dict]:
    return [{"reply": f"报价 {v} 万", "numbers": v} for v in values]


class TestComputeSimpleResult:
    def test_normal_case_price_attainment(self):
        r = compute_simple_result(SCENARIO, _prices(235, 220, 200))
        assert r["price_attainment"] == pytest.approx(0.6364, abs=1e-3)
        assert r["bottom_line_hold"] == 1.0
        assert r["score"] == pytest.approx(0.6364, abs=1e-3)

    def test_price_below_bottom_line_hold_zero(self):
        r = compute_simple_result(SCENARIO, _prices(235, 180, 170))
        assert r["bottom_line_hold"] == 0.0
        assert r["price_attainment"] == 1.0

    def test_verdict_win_draw_lose(self):
        win = compute_simple_result(SCENARIO, _prices(235, 200))
        assert win["verdict"] == "win"
        mid = compute_simple_result(SCENARIO, _prices(235, 210))
        assert mid["verdict"] == "draw"
        lose = compute_simple_result(SCENARIO, _prices(235, 170))
        assert lose["verdict"] == "lose"

    def test_no_offers_defaults(self):
        r = compute_simple_result(SCENARIO, [])
        assert r["price_attainment"] == 0.0
        assert r["bottom_line_hold"] == 1.0
        assert r["verdict"] in ("win", "draw", "lose")


class TestComputeObjectiveScore:
    def test_dimensions_and_weighted_total(self):
        offers = _prices(235, 220, 205)
        r = compute_objective_score(SCENARIO, offers)
        dims = r["dimensions"]
        assert set(dims) == {
            "price_attainment",
            "concession_margin",
            "bottom_line_hold",
            "time_efficiency",
        }
        total = sum(
            dims[k] * r["weights"][k] for k in r["weights"]
        )
        assert r["total"] == pytest.approx(total, abs=1e-9)
        assert 0 <= r["total"] <= 1

    def test_full_price_attainment(self):
        offers = _prices(235, 180)
        r = compute_objective_score(SCENARIO, offers)
        assert r["dimensions"]["price_attainment"] == pytest.approx(1.0)

    def test_zero_concession_when_no_movement(self):
        r = compute_objective_score(SCENARIO, _prices(235, 235, 235))
        assert r["dimensions"]["concession_margin"] == 0.0

    def test_time_efficiency_decreases_with_rounds(self):
        few = compute_objective_score(SCENARIO, _prices(235, 200))
        many = compute_objective_score(SCENARIO, _prices(235, 230, 225, 220, 215, 210, 205, 200))
        assert few["dimensions"]["time_efficiency"] > many["dimensions"]["time_efficiency"]


class TestGenerateReport:
    async def test_generate_report_persists_and_marks_reported(self, session, user, scenario):
        from app.services.scenario_seed import seed_scenarios

        seed_scenarios(session)
        session.commit()
        ns = NegotiationSession(
            user_id=user.id,
            scenario_id=scenario.id,
            messages_json=[
                {"role": "user", "content": "太贵了"},
                {"role": "assistant", "content": "235 万"},
                {"role": "user", "content": "200 万"},
                {"role": "assistant", "content": "200 万可以"},
            ],
            offers_json=_prices(235, 200),
        )
        session.add(ns)
        session.commit()

        async def fake_judge(history, scenario):
            return {
                "naturalness": 4.0,
                "strategy_diversity": 3.0,
                "emotion_control": 5.0,
                "logic_consistency": 4.0,
                "weak_points": ["让步过快"],
                "advice": "多使用时间压迫战术",
            }

        report = await generate_report(session, ns.id, judge=fake_judge)

        assert report.session_id == ns.id
        assert report.total_score is not None
        assert 0 <= float(report.total_score) <= 1
        obj = report.objective_json
        assert "dimensions" in obj and "total" in obj
        subj = report.subjective_json
        assert subj["dimensions"]["naturalness"] == 4.0
        assert subj["normalized"] == pytest.approx((4.0 - 1) / 4, abs=1e-6)
        assert report.weak_points == ["让步过快"]
        assert report.advice == "多使用时间压迫战术"
        assert report.concession_curve

        session.refresh(ns)
        assert ns.status == SessionStatus.REPORTED
        assert float(report.total_score) == pytest.approx(
            round(0.6 * report.objective_json["total"] + 0.4 * subj["normalized"], 2), abs=1e-9
        )

    async def test_generate_report_idempotent(self, session, user, scenario):
        from app.services.scenario_seed import seed_scenarios

        seed_scenarios(session)
        session.commit()
        ns = NegotiationSession(
            user_id=user.id,
            scenario_id=scenario.id,
            messages_json=[{"role": "user", "content": "hi"}],
            offers_json=_prices(235, 210),
        )
        session.add(ns)
        session.commit()

        async def fake_judge(history, scenario):
            return {"naturalness": 3.0, "strategy_diversity": 3.0, "emotion_control": 3.0, "logic_consistency": 3.0}

        first = await generate_report(session, ns.id, judge=fake_judge)
        second = await generate_report(session, ns.id, judge=fake_judge)
        assert second.id == first.id
        count = session.scalar(
            select(Report).where(Report.session_id == ns.id)
        )
        assert count is not None


class TestQueryReports:
    def test_list_reports_returns_owned_only(self, session, user, scenario):
        other = NegotiationSession(
            user_id=user.id,
            scenario_id="it_procurement",
            messages_json=[],
            offers_json=_prices(235, 200),
        )
        session.add(other)
        session.commit()
        session.add(
            Report(
                session_id=other.id,
                total_score=0.8,
                objective_json={"total": 0.8, "dimensions": {}},
                subjective_json={"normalized": 0.5, "dimensions": {}},
            )
        )
        session.commit()
        items = list_reports(session, user.id)
        assert len(items) == 1
        assert items[0]["session_id"] == str(other.id)
        assert items[0]["total_score"] == pytest.approx(0.8)

    def test_list_reports_isolates_users(self, session, user, scenario):
        other_user = __import__("app.models", fromlist=["User"]).User(
            email="bob@example.com", password_hash="hashed"
        )
        session.add(other_user)
        session.commit()
        ns = NegotiationSession(
            user_id=other_user.id,
            scenario_id="it_procurement",
            messages_json=[],
            offers_json=_prices(235, 210),
        )
        session.add(ns)
        session.commit()
        session.add(
            Report(
                session_id=ns.id,
                total_score=0.9,
                objective_json={"total": 0.9, "dimensions": {}},
                subjective_json={"normalized": 0.5, "dimensions": {}},
            )
        )
        session.commit()
        assert list_reports(session, user.id) == []

    def test_get_report_returns_none_for_other_user(self, session, user, scenario):
        other_user = __import__("app.models", fromlist=["User"]).User(
            email="bob2@example.com", password_hash="hashed"
        )
        session.add(other_user)
        session.commit()
        ns = NegotiationSession(
            user_id=other_user.id,
            scenario_id="it_procurement",
            messages_json=[],
            offers_json=_prices(235, 200),
        )
        session.add(ns)
        session.commit()
        rep = Report(
            session_id=ns.id,
            total_score=0.7,
            objective_json={"total": 0.7, "dimensions": {}},
            subjective_json={"normalized": 0.5, "dimensions": {}},
        )
        session.add(rep)
        session.commit()
        assert get_report(session, rep.id, user.id) is None

    def test_get_report_returns_none_for_missing(self, session, user):
        assert get_report(session, uuid.uuid4(), user.id) is None
