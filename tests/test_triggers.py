"""The fixed escalation triggers (C5)."""

from datetime import date

from agents.system import triggers
from agents.system.tools import Exclusion, all_policy_versions, get_policy, get_rule

NONE = Exclusion("no policy pinned")
V2 = get_rule(date(2025, 3, 1), False)
V1 = get_rule(date(2024, 6, 1), False)


def check(facts, rule=V2, policy=NONE, window=15, amount=500):
    return triggers.check(facts, rule, policy, window, amount)


def delayed(m, **kw):
    return {"cancelled": False, "arrival_delay_min": m, **kw}


def test_boundary_inside_and_outside_the_window():
    # @criterion C5
    for m in (165, 179, 180, 181, 195):
        assert check(delayed(m)) == ["boundary"], m
    for m in (164, 196, 0, 400):
        assert check(delayed(m)) == [], m


def test_boundary_is_around_the_threshold_that_decides():
    # @criterion C5
    delta = get_policy("DL", date(2024, 5, 1))  # 120 minutes
    assert check(delayed(125), V1, delta) == ["boundary"]
    assert check(delayed(180), V1, delta) == []
    aa = get_policy("AA", date(2024, 5, 1))  # 4 hours, but federal 3 hours is lower
    assert check(delayed(240), V1, aa) == []
    assert check(delayed(185), V1, aa) == ["boundary"]


def test_cancelled_has_no_boundary():
    # @criterion C5
    f = {"cancelled": True, "alternative_accepted": False, "arrival_delay_min": 180}
    assert check(f) == []


def test_missing_fact_that_changes_the_answer():
    # @criterion C5
    f = {"cancelled": True, "alternative_offered": True}
    assert check(f) == ["missing_fact:alternative_accepted"]
    assert check({"cancelled": False}) == ["missing_fact:arrival_delay_min"]
    f = {"cancelled": False, "arrival_delay_min": 10, "renumbered": True}
    assert check(f, get_rule(date(2026, 2, 1), True)) == [
        "missing_fact:significant_change"
    ]


def test_missing_fact_that_does_not_change_the_answer_is_silent():
    # @criterion C5
    # alternative_accepted is moot when none was offered; significant_change before the pause
    assert check({"cancelled": True, "alternative_offered": False}) == []
    f = {"cancelled": False, "arrival_delay_min": 10, "renumbered": True}
    assert check(f, get_rule(date(2025, 3, 1), True)) == []
    # purchase_date is moot at 250 minutes: every Delta version refunds
    assert check(delayed(250), V1, all_policy_versions("DL")) == []


def test_missing_purchase_date_that_matters():
    # @criterion C5
    pols = all_policy_versions("DL")
    assert check(delayed(150), V1, pols, window=0) == ["missing_fact:purchase_date"]
    # candidate thresholds 120 and 180: a delay near either is a boundary too
    assert "boundary" in check(delayed(125), V1, pols, window=10)


def test_amount_over_and_under():
    # @criterion C5
    assert check(delayed(0, amount=501)) == ["amount"]
    assert check(delayed(0, amount=500)) == []
    assert check(delayed(0)) == []


def test_out_of_scope_request():
    # @criterion C5
    for kind in ("international", "baggage", "compensation"):
        assert check(delayed(0, request_kind=kind)) == ["out_of_scope"]
    assert check(delayed(0, cited_carrier="Delta")) == []


def test_excluded_rule_is_the_only_reason():
    # @criterion C5
    r = get_rule(date(2026, 7, 3), True)
    assert isinstance(r, Exclusion)
    assert check({"cancelled": False, "renumbered": True}, r) == ["excluded_rule"]


def test_policy_exclusion_gives_no_reason():
    # @criterion C5
    assert check(delayed(0), V2, Exclusion("none covers")) == []
