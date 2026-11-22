"""The rule engine decides from facts, rule version and policy (C3)."""

import itertools
from datetime import date

import pytest

from agents.system import engine
from agents.system.tools import (
    Exclusion,
    all_policy_versions,
    all_rule_versions,
    get_policy,
    get_rule,
)

NONE = Exclusion("no policy pinned")


def rule(d, renumbered=False):
    return get_rule(date.fromisoformat(d), renumbered)


def pol(carrier, d):
    return get_policy(carrier, date.fromisoformat(d))


def dec(facts, r, p):
    return engine.decide(facts, r, p)


def delayed(minutes, **kw):
    return {"cancelled": False, "arrival_delay_min": minutes, **kw}


@pytest.mark.parametrize(
    "minutes,want", [(179, "no_refund"), (180, "refund"), (181, "refund")]
)
def test_v2_three_hour_boundary(minutes, want):
    # @criterion C3
    out = dec(delayed(minutes), rule("2025-03-01"), NONE)
    assert out["decision"] == want
    assert out["clause"] == "v2-260.2-delay"
    assert out["rule_version"] == "v2"
    assert out["policy_version"] is None


def test_v2_boundary_with_delta_policy():
    # @criterion C3
    p = pol("DL", "2025-01-10")
    assert [
        dec(delayed(m), rule("2025-03-01"), p)["decision"] for m in (179, 180, 181)
    ] == [
        "no_refund",
        "refund",
        "refund",
    ]


def test_v1_federal_three_hours():
    # @criterion C3
    assert (
        dec(delayed(180), rule("2024-07-01"), NONE)["clause"]
        == "v1-42305-delay-definition"
    )
    assert dec(delayed(179), rule("2024-07-01"), NONE)["decision"] == "no_refund"


def test_old_delta_is_strictly_greater_than_120():
    # @criterion C3
    p = pol("DL", "2024-05-01")
    r = rule("2024-06-01")
    assert dec(delayed(120), r, p)["decision"] == "no_refund"
    out = dec(delayed(121), r, p)
    assert out["decision"] == "refund"
    assert out["clause"] == "DL-2024-03-12-19A-schedule-change"


def test_old_american_four_hours_yields_to_federal_three():
    # @criterion C3
    p = pol("AA", "2024-05-01")
    assert (
        dec(delayed(200), rule("2024-06-01"), p)["clause"]
        == "v1-42305-delay-definition"
    )
    # before the statute, the contract's own four hours is all there is
    assert dec(delayed(200), rule("2024-03-01"), p)["decision"] == "no_refund"
    assert dec(delayed(241), rule("2024-03-01"), p)["decision"] == "refund"


def test_v0_without_policy_has_no_threshold_and_escalates():
    # @criterion C3
    assert dec(delayed(200), rule("2024-03-01"), NONE)["decision"] == "escalate"


@pytest.mark.parametrize("accepted,want", [(False, "refund"), (True, "no_refund")])
def test_cancellation_with_and_without_alternative_accepted(accepted, want):
    # @criterion C3
    f = {
        "cancelled": True,
        "alternative_offered": True,
        "alternative_accepted": accepted,
    }
    for d in ("2024-03-01", "2024-07-01", "2025-03-01"):
        assert dec(f, rule(d), NONE)["decision"] == want
    assert dec(f, rule("2025-03-01"), pol("DL", "2025-01-10"))["decision"] == want


def test_no_alternative_offered_cannot_be_accepted():
    # @criterion C3
    f = {"cancelled": True, "alternative_offered": False}
    assert dec(f, rule("2025-03-01"), NONE)["decision"] == "refund"


@pytest.mark.parametrize("sig,want", [(True, "refund"), (False, "no_refund")])
@pytest.mark.parametrize(
    "day,clause",
    [("2026-02-01", "v3-fr-pause-renumbered"), ("2026-09-01", "v4-fr-pause-extension")],
)
def test_renumbered_with_and_without_significant_change(sig, want, day, clause):
    # @criterion C3
    f = {
        "cancelled": False,
        "arrival_delay_min": 10,
        "renumbered": True,
        "significant_change": sig,
    }
    out = dec(f, rule(day, True), NONE)
    assert (out["decision"], out["clause"]) == (want, clause)


def test_renumbered_before_the_pause_is_a_cancelled_flight():
    # @criterion C3
    f = {
        "cancelled": False,
        "arrival_delay_min": 10,
        "renumbered": True,
        "significant_change": False,
    }
    out = dec(f, rule("2025-03-01", True), NONE)
    assert (out["decision"], out["clause"]) == ("refund", "v2-260.2-cancelled")


def test_american_flight_number_change_is_a_cancellation_even_in_the_pause():
    # @criterion C3
    f = {
        "cancelled": False,
        "arrival_delay_min": 10,
        "renumbered": True,
        "significant_change": False,
    }
    out = dec(f, rule("2026-02-01", True), pol("AA", "2025-10-10"))
    assert (out["decision"], out["clause"]) == (
        "refund",
        "AA-2025-06-27-automatic-refund",
    )
    # the 2026 copies dropped the sentence: the pause spares the flight again
    out = dec(f, rule("2026-02-01", True), pol("AA", "2026-04-20"))
    assert (out["decision"], out["clause"]) == ("no_refund", "v3-fr-pause-renumbered")


def test_renumbered_in_the_gap_is_excluded():
    # @criterion C3
    r = rule("2026-07-03", True)
    assert isinstance(r, Exclusion)
    out = dec({"cancelled": False, "arrival_delay_min": 0, "renumbered": True}, r, NONE)
    assert (out["decision"], out["clause"], out["rule_version"]) == (
        "escalate",
        "excluded_rule",
        None,
    )


def test_renumbered_before_v2_is_open():
    # @criterion C3
    f = {
        "cancelled": False,
        "arrival_delay_min": 10,
        "renumbered": True,
        "significant_change": False,
    }
    assert dec(f, rule("2024-07-01", True), NONE)["decision"] == "escalate"
    f["significant_change"] = True
    assert dec(f, rule("2024-07-01", True), NONE)["decision"] == "refund"


@pytest.mark.parametrize("kind", ["international", "baggage", "compensation"])
def test_out_of_scope_request_escalates(kind):
    # @criterion C3
    out = dec({**delayed(300), "request_kind": kind}, rule("2025-03-01"), NONE)
    assert (out["decision"], out["clause"]) == ("escalate", "out_of_scope")


def test_cited_carrier_changes_nothing():
    # @criterion C3
    f = delayed(150)
    p = pol("DL", "2024-05-01")
    assert dec({**f, "cited_carrier": "American"}, rule("2024-06-01"), p) == dec(
        f, rule("2024-06-01"), p
    )


def test_missing_fact_that_changes_nothing_does_not_escalate():
    # @criterion C3
    # 250 minutes is a refund under every Delta and every federal version
    out = dec(
        {"cancelled": False, "arrival_delay_min": 250},
        rule("2024-06-01"),
        all_policy_versions("DL"),
    )
    assert out["decision"] == "refund"
    # 100 minutes is no refund under every Delta version (thresholds 120 and 180)
    out = dec(
        {"cancelled": False, "arrival_delay_min": 100},
        rule("2024-06-01"),
        all_policy_versions("DL"),
    )
    assert out["decision"] == "no_refund"


def test_missing_purchase_date_that_matters_cites_the_airline_clause():
    # @criterion C3
    out = dec(delayed(150), rule("2024-06-01"), all_policy_versions("DL"))
    assert (out["decision"], out["clause"]) == ("escalate", "DL-19A-schedule-change")
    out = dec(delayed(200), rule("2024-03-01"), all_policy_versions("AA"))
    assert (out["decision"], out["clause"]) == ("escalate", "AA-delay-refund")


def test_missing_alternative_accepted_escalates():
    # @criterion C3
    f = {"cancelled": True, "alternative_offered": True}
    assert dec(f, rule("2025-03-01"), NONE)["decision"] == "escalate"


def test_missing_significant_change_only_matters_in_the_pause():
    # @criterion C3
    f = {"cancelled": False, "arrival_delay_min": 10, "renumbered": True}
    assert dec(f, rule("2026-02-01", True), NONE)["decision"] == "escalate"
    assert dec(f, rule("2025-03-01", True), NONE)["decision"] == "refund"


def test_missing_delay_escalates_unless_cancelled():
    # @criterion C3
    assert dec({"cancelled": False}, rule("2025-03-01"), NONE)["decision"] == "escalate"
    assert (
        dec(
            {"cancelled": True, "alternative_accepted": False}, rule("2025-03-01"), NONE
        )["decision"]
        == "refund"
    )


def _scenarios():
    rules = [
        rule(d)
        for d in ("2024-03-01", "2024-07-01", "2025-03-01", "2026-02-01", "2026-09-01")
    ]
    rules += [
        rule("2026-02-01", True),
        rule("2026-09-01", True),
        rule("2025-03-01", True),
    ]
    rules += [rule("2024-07-01", True), rule("2026-07-03", True)]
    pols = [NONE] + [p for c in ("DL", "AA") for p in all_policy_versions(c)]
    pols += [all_policy_versions("DL"), all_policy_versions("AA")]
    facts = [
        {
            "cancelled": c,
            "arrival_delay_min": d,
            "alternative_offered": True,
            "alternative_accepted": a,
            "renumbered": rn,
            "significant_change": s,
        }
        for c, d, a, rn, s in itertools.product(
            (True, False),
            (0, 100, 150, 200, 250),
            (True, False),
            (True, False),
            (True, False),
        )
    ]
    facts += [
        {"cancelled": False, "arrival_delay_min": 150},
        {"cancelled": True},
        {"request_kind": "baggage"},
    ]
    for r, p, f in itertools.product(rules, pols, facts):
        yield f, r, p


def test_every_clause_has_a_positive_and_a_negative_example():
    # @criterion C3
    seen = {}
    for f, r, p in _scenarios():
        out = dec(f, r, p)
        assert out["clause"] in engine.CLAUSES or out["clause"] is None
        seen.setdefault(out["clause"], 0)
        seen[out["clause"]] += 1
    total = sum(seen.values())
    for cid in engine.CLAUSES:
        assert seen.get(cid, 0) > 0, f"no positive example for {cid}"
        assert seen[cid] < total, f"no negative example for {cid}"


def test_clauses_name_real_clauses():
    # @criterion C3
    ids = {c.id for r in all_rule_versions() for c in r.clauses}
    ids |= {
        c.id for k in ("DL", "AA") for p in all_policy_versions(k) for c in p.clauses
    }
    for cid in engine.CLAUSES:
        assert (
            cid in ids
            or cid in ("excluded_rule", "out_of_scope")
            or cid in ("DL-19A-schedule-change", "AA-delay-refund")
        )


def test_gap_candidates_that_disagree_escalate():
    # @criterion C3
    # one candidate says "a flight number change is considered a cancellation", one does not
    cands = get_policy("AA", date(2026, 3, 15))
    assert [p.id for p in cands] == ["AA-2025-06-27", "AA-2026-03-02"]
    f = {
        "cancelled": False,
        "arrival_delay_min": 10,
        "renumbered": True,
        "significant_change": False,
        "purchase_date": "2026-03-15",
    }
    out = dec(f, rule("2026-02-01", True), cands)
    assert out["decision"] == "escalate"
    assert out["clause"] == "v3-fr-pause-renumbered"
    assert out["policy_version"] == "AA-2025-06-27;AA-2026-03-02"
    assert engine.missing_facts(f, rule("2026-02-01", True), cands) == []


def test_gap_candidates_that_agree_give_the_shared_decision():
    # @criterion C3
    cands = get_policy("AA", date(2024, 8, 1))
    f = delayed(200, purchase_date="2024-08-01")
    out = dec(f, rule("2024-09-15"), cands)
    assert out["decision"] == "refund"
    assert out["policy_version"] == "AA-2024-04-12;AA-2024-07-25"
    assert engine.missing_facts(f, rule("2024-09-15"), cands) == []


def test_no_saved_policy_candidate_escalates_a_missing_purchase_date():
    # @criterion C3
    from rules.lookup import purchase_candidates

    cands = purchase_candidates("AA", date(2024, 3, 15))
    assert [p.id if p else None for p in cands] == ["AA-2023-10-10", None]
    r = rule("2024-03-15")
    f = delayed(30)
    assert dec(f, r, cands[0])["decision"] == "no_refund"
    out = dec(f, r, cands)
    assert out["decision"] == "escalate"
    assert "purchase_date" in engine.missing_facts(f, r, cands)
    # cancelled, alternative refused: every candidate refunds
    c = {"cancelled": True, "renumbered": False, "alternative_offered": False}
    c["alternative_accepted"] = False
    assert dec(c, r, cands)["decision"] == "refund"
