from pathlib import Path

import yaml

from eval import metrics
from eval.subset import draw

ENT = yaml.safe_load(metrics.ENTITLEMENTS.read_text())
TABLE = {
    "versions": [
        {"id": "v1", "first_day": "2024-05-16", "last_day": "2024-10-27"},
        {"id": "v2", "first_day": "2024-10-28", "last_day": None},
    ]
}


def case(cid, type_="x", **kw):
    return {
        "case_id": cid,
        "carrier": "DL",
        "flight_date": "2024-07-01",
        "type": type_,
        **kw,
    }


def label(decision):
    return {
        "decision": decision,
        "rule_version": "v1",
        "policy_version": "DL-2024-03-12",
    }


def out(cid, decision, explanation="No entitlement stated.", **kw):
    return {
        "case_id": cid,
        "run": 0,
        "decision": decision,
        "explanation": explanation,
        "dollars": 0.5,
        "latency": 2.0,
        "cache_hits": 1,
        **kw,
    }


# (case, label, output): one of each outcome, the rest correct and clean
FIXTURE = [
    (case("c1"), "refund", out("c1", "refund")),
    (case("c2"), "refund", out("c2", "no_refund")),  # wrong decision
    (case("c3"), "escalate", out("c3", "refund")),  # missed escalation
    (case("c4"), "no_refund", out("c4", "escalate")),  # unnecessary escalation
    (case("c5"), "escalate", out("c5", "escalate")),  # needed escalation
    (case("c6"), "refund", out("c6", "refund", "Under v2 you are owed it.")),  # version
    (case("c7"), "refund", out("c7", "refund", "You get a Voucher.")),  # invented
    (
        case("c8"),
        "refund",
        out("c8", "refund", "See AA-2024-04-12-delay-refund."),  # policy leak
    ),
    (case("c9", "clean"), "no_refund", out("c9", "no_refund")),
    (
        case("c10", "adversarial", clean_case_id="c9"),
        "refund",
        out("c10", "refund"),  # adversarial change (clean modal is no_refund)
    ),
    (case("c11"), "refund", out("c11", "refund", parse_error=True)),  # parse error
]


def run_metrics(fixture=FIXTURE, latency=2.0):
    cases = [c for c, _, _ in fixture]
    labels = {c["case_id"]: label(d) for c, d, _ in fixture}
    return metrics.agent_metrics(
        cases, labels, [o for _, _, o in fixture], TABLE, ENT, latency=latency
    )


def test_counts_known():
    # @criterion C2
    m = run_metrics()["overall"]
    assert m["runs"] == 11
    assert m["wrong_decisions"] == 1 and m["missed_escalations"] == 1
    assert m["critical_errors"] == 2
    assert m["wrong_decisions_per_100"] == 100 / 11
    assert m["missed_escalations_per_100"] == 100 / 11


def test_escalations_apart_from_critical_errors():
    # @criterion C5
    m = run_metrics()["overall"]
    assert m["needed_escalations"] == 1 and m["unnecessary_escalations"] == 1
    assert m["unnecessary_escalations_per_100"] == 100 / 11
    # the escalations never enter the critical count
    assert m["critical_errors"] == m["wrong_decisions"] + m["missed_escalations"]


def test_versions_entitlements_leaks_parse_errors():
    # @criterion C11
    m = run_metrics()["overall"]
    assert m["version_errors"] == 1
    assert m["invented_entitlements"] == 1
    assert m["policy_leaks"] == 1
    assert m["policy_leaks_per_100"] == 100 / 11
    assert m["parse_errors"] == 1


def test_adversarial_change_against_clean_mode():
    # @criterion C7
    m = run_metrics()["overall"]
    assert (m["adversarial_runs"], m["adversarial_changes"]) == (1, 1)
    assert m["adversarial_change_share"] == 1.0
    by_type = run_metrics()["by_type"]
    assert by_type["adversarial"]["adversarial_change_share"] == 1.0
    assert by_type["clean"]["runs"] == 1


def test_cost_and_latency_per_unit():
    # @criterion C8
    m = run_metrics()["overall"]
    correct = m["correct"]  # c1, c5, c6, c7, c8, c9, c10, c11
    assert correct == 8
    assert m["dollars"] == 5.5
    assert m["cost_per_correct_decision"] == 5.5 / 8
    assert m["latency_per_answer"] == 2.0
    assert m["cache_hits"] == 11


def test_version_error_by_date_not_by_label():
    # @criterion C2
    c = case("a", flight_date="2024-11-01")
    assert not metrics.version_error({"explanation": "per v2"}, c, TABLE)
    assert metrics.version_error({"explanation": "per v1"}, c, TABLE)
    assert metrics.version_error({"explanation": "x", "rule_version": "v1"}, c, TABLE)


def test_subset_draw_has_each_type_and_twins():
    # @criterion C7
    cases = []
    for t in "abcd":
        cases += [case(f"{t}{i}", t) for i in range(10)]
    cases += [case(f"adv{i}", "adv", clean_case_id=f"a{i}") for i in range(6)]
    ids = draw(cases, seed=1, size=20, per_type=3)
    assert len(ids) == 20 and ids == draw(cases, seed=1, size=20, per_type=3)
    by_id = {c["case_id"]: c for c in cases}
    assert all(sum(by_id[i]["type"] == t for i in ids) >= 3 for t in "abcd")
    for i in ids:
        if by_id[i].get("clean_case_id"):
            assert by_id[i]["clean_case_id"] in ids


def test_committed_subset_is_the_seeded_draw():
    # @criterion C2
    root = Path(__file__).resolve().parent.parent
    cases = metrics.read_jsonl(root / "cases/dev/cases.jsonl")
    ids = (root / "cases/dev/subset.txt").read_text().split()
    assert ids == draw(cases) and len(ids) == 40


def test_inherited_version_is_in_force():
    # @criterion C2
    table = {
        "versions": [
            {"id": "v1", "first_day": "2024-05-16", "last_day": "2024-10-27"},
            {"id": "v2", "first_day": "2024-10-28", "last_day": "2025-12-04"},
            {"id": "v3", "first_day": "2025-12-05", "last_day": None, "follows": "v2"},
        ]
    }
    c = case("a", flight_date="2026-01-10")
    assert not metrics.version_error({"explanation": "per v2"}, c, table)
    assert metrics.version_error({"explanation": "per v1"}, c, table)


def test_latency_from_the_cost_lines(tmp_path):
    # @criterion C8
    # Outputs carry no latency that counts every call; the cost lines do, cache hits
    # included: 1.5 + 0.25 + 2.25 seconds over 2 case-runs.
    d = tmp_path / "run"
    (d / "outputs").mkdir(parents=True)
    for i in range(2):
        (d / "outputs" / f"c1_{i}.json").write_text('{"case_id": "c1", "latency": 9}')
    (d / "costs.jsonl").write_text(
        '{"dollars": 0.1, "latency": 1.5, "cache": false}\n'
        '{"dollars": 0.0, "latency": 0.25, "cache": true}\n'
        '{"dollars": 0.1, "latency": 2.25, "cache": false}\n'
    )
    assert metrics.load_latency_total(d) == 4.0
    assert metrics.latency_per_answer(d) == 2.0
    assert metrics.latency_per_answer(tmp_path / "none") is None
    m = run_metrics(latency=metrics.latency_per_answer(d))
    assert m["overall"]["latency_per_answer"] == 2.0
    # a case type has no latency of its own: cost lines carry no case id
    assert m["by_type"]["x"]["latency_per_answer"] is None


def test_version_error_clause_id_in_rule_version_field():
    c = case("a", flight_date="2024-11-01")
    out = {"explanation": "x", "rule_version": "v2-260.2-cancelled"}
    assert not metrics.version_error(out, c, TABLE)
    assert metrics.version_error_registered(out, c, TABLE)
    old = {"explanation": "x", "rule_version": "v1"}
    assert metrics.version_error(old, c, TABLE)
    assert metrics.version_error_registered(old, c, TABLE)
