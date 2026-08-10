"""战术规则引擎测试：覆盖 PRD 9.7 条件表与多步战术续接。"""


from app.engine.tactics import (
    CONCESSION_BAIT,
    DEADLOCK_BREAK,
    DEFAULT_TACTIC,
    DIVIDE_CONQUER,
    FALSE_BOTTOM,
    GOOD_COP_BAD_COP,
    INFO_ASYMMETRY,
    LAST_ULTIMATUM,
    SILENCE_PRESSURE,
    TIME_PRESSURE,
    TacticContext,
    TacticDecision,
    select_tactic,
    update_tactic_context,
)


def ctx(**kw) -> TacticContext:
    defaults = {"round": 1, "scenario": {}, "user_intent": {}}
    defaults.update(kw)
    return TacticContext(**defaults)


class TestRulePriority:
    def test_deadlock_break(self):
        c = ctx(phase="deadlock", rounds_since_last_progress=4)
        assert select_tactic(c).name == DEADLOCK_BREAK

    def test_deadlock_not_triggered_below_threshold(self):
        c = ctx(phase="deadlock", rounds_since_last_progress=2)
        assert select_tactic(c).name == DEFAULT_TACTIC

    def test_last_ultimatum_in_closing(self):
        c = ctx(phase="closing", user_concede_count=0)
        assert select_tactic(c).name == LAST_ULTIMATUM

    def test_time_pressure(self):
        c = ctx(round=3, scenario={"time_sensitive": True})
        assert select_tactic(c).name == TIME_PRESSURE

    def test_time_pressure_not_before_round3(self):
        c = ctx(round=2, scenario={"time_sensitive": True}, user_firmness="high")
        assert select_tactic(c).name == DEFAULT_TACTIC

    def test_false_bottom_on_high_aggression(self):
        c = ctx(phase="core", user_intent={"aggression_level": "high"})
        assert select_tactic(c).name == FALSE_BOTTOM

    def test_divide_conquer_multi_dimension(self):
        c = ctx(
            phase="core",
            scenario={"multi_dimension": True, "dimension_total": 4, "dimension_agreement_count": 1},
        )
        assert select_tactic(c).name == DIVIDE_CONQUER

    def test_divide_conquer_skip_when_most_agreed(self):
        c = ctx(
            phase="core",
            scenario={"multi_dimension": True, "dimension_total": 4, "dimension_agreement_count": 3},
        )
        assert select_tactic(c).name == DEFAULT_TACTIC

    def test_good_cop_bad_cop_round4(self):
        c = ctx(phase="core", round=4)
        d = select_tactic(c)
        assert d.name == GOOD_COP_BAD_COP
        assert d.sub_role == "bad_cop"
        assert d.step == 1

    def test_silence_pressure(self):
        c = ctx(round=2, user_intent={"emotion": "eager"}, last_user_msg_length=5)
        assert select_tactic(c).name == SILENCE_PRESSURE

    def test_concession_bait(self):
        c = ctx(round=2, user_firmness="low", user_intent={})
        assert select_tactic(c).name == CONCESSION_BAIT

    def test_info_asymmetry_once_per_session(self):
        c = ctx(round=2, user_firmness="high", scenario={"has_insider_info": True}, used_tactics=[])
        assert select_tactic(c).name == INFO_ASYMMETRY
        c.used_tactics = [INFO_ASYMMETRY]
        assert select_tactic(c).name != INFO_ASYMMETRY

    def test_default_fallback(self):
        c = ctx(round=1, phase="opening", user_intent={}, scenario={})
        assert select_tactic(c).name == DEFAULT_TACTIC


class TestMultiStep:
    def test_continuation(self):
        tc = update_tactic_context({}, TacticDecision(name=GOOD_COP_BAD_COP, sub_role="bad_cop", step=1))
        assert tc["active_tactic"] == GOOD_COP_BAD_COP
        assert tc["step"] == 1

        d = select_tactic(ctx(round=5, tactic_context=tc))
        assert d.name == GOOD_COP_BAD_COP
        assert d.sub_role == "good_cop"
        assert d.step == 2

    def test_completion_resets_context(self):
        tc = update_tactic_context(
            {"active_tactic": GOOD_COP_BAD_COP, "step": 1},
            TacticDecision(name=GOOD_COP_BAD_COP, sub_role="good_cop", step=2),
        )
        assert tc["active_tactic"] == ""
        assert tc["step"] == 0

    def test_completed_multi_step_allows_new_tactic(self):
        tc = {"active_tactic": "", "step": 0}
        d = select_tactic(ctx(phase="closing", user_concede_count=0, tactic_context=tc))
        assert d.name == LAST_ULTIMATUM


class TestOtherTactics:
    def test_all_tactics_have_prompts_and_safe_templates(self):
        from app.engine.tactics import SAFE_TEMPLATES, TACTIC_PROMPTS

        for name in (
            GOOD_COP_BAD_COP, TIME_PRESSURE, LAST_ULTIMATUM, FALSE_BOTTOM,
            DIVIDE_CONQUER, SILENCE_PRESSURE, CONCESSION_BAIT, INFO_ASYMMETRY,
        ):
            assert name in TACTIC_PROMPTS, name
            assert SAFE_TEMPLATES.get(name), name
