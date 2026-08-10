"""实时分数推送测试（PRD 8.2 协议 meta.score / 故事 3）：_meta_from_state 含 score。"""

from app.api.negotiation import _meta_from_state
from app.scenarios import load_scenario


def _state_with_offers(prices):
    scenario = load_scenario("it_procurement")
    offers = [{"round": i + 1, "numbers": p, "label": "总价"} for i, p in enumerate(prices)]
    return {"scenario": scenario, "offers_json": offers, "intent": {"intent_type": "offer"}}


class TestMetaScore:
    def test_meta_contains_score_field(self):
        meta = _meta_from_state(_state_with_offers([235, 210, 200]))
        assert "score" in meta, "meta 应携带实时分数（PRD 8.2 协议字段）"
        assert 0.0 <= meta["score"] <= 1.0

    def test_score_reflects_price_progress(self):
        """报价越接近目标价，分数越高。"""
        low = _meta_from_state(_state_with_offers([235]))["score"]
        high = _meta_from_state(_state_with_offers([235, 200, 185]))["score"]
        assert high > low

    def test_meta_still_has_existing_fields(self):
        meta = _meta_from_state(_state_with_offers([235]))
        assert meta["tactic"] == ""
        assert meta["bottom_line"] == "ok"
        assert meta["round"] == 1
