"""The confirmatory report (T40, prereg sections 1, 5 and 6), on a fixture tree: fake test
cases over three carrier-months, fake frozen answers, fake outputs and cost lines. No real
confirmatory run is read and no model is called."""

import json
import shutil
from pathlib import Path

import pytest

from eval import confirm as ec
from eval.consistency import case_consistent
from eval.metrics import modal, modal_or_escalate
from report import confirm as rc

REPO = Path(__file__).resolve().parent.parent
AGENTS = ("naive", "cheap_strong", "system")
R = 10


def case(cid, carrier, date, type_="cancelled", **kw):
    return {
        "case_id": cid,
        "carrier": carrier,
        "flight_number": "100",
        "flight_date": date,
        "type": type_,
        "facts": {},
        "message": {"text": "x", "constructed": True},
        **kw,
    }


# Three clusters: DL-2024-07, DL-2024-08, AA-2024-07, two cases each.
CASES = [
    case("a1", "DL", "2024-07-01"),
    case("a2", "DL", "2024-07-02"),
    case("b1", "DL", "2024-08-01", "delay_above"),
    case("b2", "DL", "2024-08-02", "adversarial", clean_case_id="b1"),
    case("c1", "AA", "2024-07-01", "missing_fact"),
    case("c2", "AA", "2024-07-02", "adversarial", clean_case_id="c1"),
]
LABEL = {
    "a1": "refund",
    "a2": "no_refund",
    "b1": "refund",
    "b2": "refund",
    "c1": "escalate",
    "c2": "escalate",
}
DOT_CASE = {
    "case_id": "dot-p1",
    "carrier": None,
    "flight_number": None,
    "flight_date": None,
    "type": "dot_example",
    "facts": {},
    "message": {"text": "x", "constructed": True},
}
DOT_ANSWER = "no_refund"


def runs(**counts):
    out = []
    for d, n in counts.items():
        out += [d] * n
    assert len(out) == R
    return out


DECISIONS = {
    "system": {cid: [d] * R for cid, d in LABEL.items()}
    | {"dot-p1": ["no_refund"] * R},
    "naive": {
        "a1": runs(refund=9, no_refund=1),  # 1 wrong, inconsistent
        "a2": runs(no_refund=10),
        "b1": runs(refund=5, no_refund=5),  # 5 wrong, tied mode: escalate
        "b2": runs(refund=10),  # differs from the tied clean mode: 10 changes
        "c1": runs(escalate=10),
        "c2": runs(refund=4, escalate=6),  # 4 missed, 4 changes
        "dot-p1": runs(refund=10),
    },
    "cheap_strong": {
        "a1": runs(refund=10),
        "a2": runs(no_refund=10),
        "b1": runs(refund=10),
        "b2": runs(refund=10),
        "c1": runs(escalate=9, refund=1),  # 1 missed, inconsistent
        "c2": runs(escalate=10),
        "dot-p1": runs(refund=7, no_refund=3),
    },
}
DOLLARS = {"naive": 0.5, "cheap_strong": 1.0, "system": 0.25}
COST_LINES = {
    "naive": [(1.0, "fake-study-20261101", False), (0.5, "fake-study-20261101", True)],
    "cheap_strong": [(2.0, "fake-study-20261101", False)] * 3,
    "system": [(1.0, "fake-study-20261101", False), (3.0, None, True)],
}
PREREG = """# Prereg

- **Operating point:** window=0 min
- **Operating point grid:** full development set, system agent.

| window (min) | critical errors | unnecessary escalations |
|---|---|---|
| 0 | 20 | 50 |
| 5 | 20 | 130 |

- **Registration commit:** x
"""
COMPLETE = {
    "date": "2026-11-20",
    "tag": "prereg-v1",
    "tag_commit": "0123abcd" * 5,
    "test_hash": "f" * 64,
    "model": "fake-study",
    "dollars": DOLLARS,
}


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def write_outputs(runs_dir, agent, decisions, extra=None):
    d = runs_dir / f"confirm-{agent}"
    (d / "outputs").mkdir(parents=True, exist_ok=True)
    for cid, ds in decisions.items():
        for i, dec in enumerate(ds):
            out = {
                "case_id": cid,
                "run": i,
                "decision": dec,
                "explanation": "No entitlement stated.",
                "parse_error": False,
                "network_error": False,
                "dollars": 0.0,
            }
            out.update((extra or {}).get((cid, i), {}))
            (d / "outputs" / f"{cid}_{i}.json").write_text(json.dumps(out))
    jsonl(
        d / "costs.jsonl",
        [
            {"dollars": 0.0, "latency": lat, "response_model": m, "cache": hit}
            for lat, m, hit in COST_LINES[agent]
        ],
    )


def build(tmp_path, cases=CASES, labels=LABEL, decisions=DECISIONS, extra=None):
    root = tmp_path
    jsonl(root / "cases/test/cases.jsonl", cases)
    jsonl(root / "cases/test/dot/cases.jsonl", [DOT_CASE])
    jsonl(
        root / "data/labels/labels.jsonl",
        [
            {
                "case_id": cid,
                "decision": d,
                "clause": "x",
                "rule_version": "v1",
                "policy_version": "DL-2024-03-12",
            }
            for cid, d in labels.items()
        ],
    )
    jsonl(
        root / "data/labels/dot/answers.jsonl",
        [{"case_id": "dot-p1", "answer": DOT_ANSWER, "citation": "p1"}],
    )
    (root / "rules").mkdir(exist_ok=True)
    shutil.copy(REPO / "rules/versions.yaml", root / "rules/versions.yaml")
    (root / "docs/modules").mkdir(parents=True, exist_ok=True)
    (root / "docs/modules/prereg.md").write_text(PREREG)
    runs_dir = root / "runs"
    (runs_dir / "confirm").mkdir(parents=True, exist_ok=True)
    (runs_dir / "confirm/complete.json").write_text(json.dumps(COMPLETE))
    for a in AGENTS:
        write_outputs(runs_dir, a, decisions[a], (extra or {}).get(a))
    return root


def analyze(root):
    tests = [json.loads(x) for x in (root / "cases/test/cases.jsonl").open()]
    return ec.analyze(root, root / "runs", tests, [DOT_CASE])


def comparison(report, h, other):
    return next(c for c in report["primary"][h]["comparisons"] if c["other"] == other)


def test_primary_values_by_hand(tmp_path):
    # @criterion C1
    r = analyze(build(tmp_path))
    p = r["primary"]
    assert p["H1"]["values"] == {"naive": 0.5, "cheap_strong": 5 / 6, "system": 1.0}
    assert p["H2"]["values"] == pytest.approx(
        {"naive": 1000 / 60, "cheap_strong": 100 / 60, "system": 0.0}
    )
    assert p["H2"]["wrong_decisions_per_100"]["naive"] == pytest.approx(600 / 60)
    assert p["H2"]["missed_escalations_per_100"]["naive"] == pytest.approx(400 / 60)
    assert p["H3"]["values"] == pytest.approx(
        {"naive": 0.7, "cheap_strong": 0.0, "system": 0.0}
    )
    assert p["H1"]["clusters"] == 3 and p["H3"]["clusters"] == 2


def test_primary_paired_differences_and_intervals_by_hand(tmp_path):
    # @criterion C1
    r = analyze(build(tmp_path))
    # H1: every cluster gives system 2/2 and naive 1/2, so every resample differs by 0.5
    c = comparison(r, "H1", "naive")
    assert (c["difference"], c["low"], c["high"]) == (0.5, 0.5, 0.5)
    # cheap-strong misses only in AA-2024-07: no AA cluster drawn (8/27 of the draws) gives
    # 0, all three AA (1/27 > 2.5%) gives 0.5
    c = comparison(r, "H1", "cheap_strong")
    assert c["difference"] == pytest.approx(1 / 6) and (c["low"], c["high"]) == (0, 0.5)
    c = comparison(r, "H2", "cheap_strong")
    assert c["difference"] == pytest.approx(-100 / 60)
    assert (c["low"], c["high"]) == (-5.0, 0.0)
    c = comparison(r, "H2", "naive")
    assert c["difference"] == pytest.approx(-1000 / 60) and c["high"] <= -5.0
    c = comparison(r, "H3", "naive")
    assert c["difference"] == pytest.approx(-0.7)
    assert (c["low"], c["high"]) == pytest.approx((-1.0, -0.4))
    assert [x["other"] for x in r["primary"]["H3"]["comparisons"]] == ["naive"]
    meets = {
        (h, c["other"]): c["meets_criterion"]
        for h, p in r["primary"].items()
        for c in p["comparisons"]
    }
    assert meets == {
        ("H1", "naive"): True,
        ("H1", "cheap_strong"): False,
        ("H2", "naive"): True,
        ("H2", "cheap_strong"): False,
        ("H3", "naive"): True,
    }
    verdicts = {h: p["verdict"] for h, p in r["primary"].items()}
    assert verdicts == {
        "H1": "not confirmed",
        "H2": "not confirmed",
        "H3": "confirmed",
    }


def test_primary_bootstrap_repeatable_with_the_seed(tmp_path):
    # @criterion C1
    root = build(tmp_path)
    assert analyze(root)["primary"] == analyze(root)["primary"]


def test_mapping_tied_clean_mode_counts_as_escalate():
    # @criterion C7
    tied = ["refund"] * 5 + ["no_refund"] * 5
    assert modal_or_escalate(tied) == "escalate"
    assert modal(tied) == "refund"  # the development report's rule stays as it was
    assert modal_or_escalate(["refund"] * 6 + ["no_refund"] * 4) == "refund"
    assert modal_or_escalate(["refund", "no_refund", "escalate"]) == "escalate"


def test_mapping_h3_uses_the_tie_rule(tmp_path):
    # @criterion C7
    # naive's b1 ties 5-5: its mode is escalate, so all ten refund runs of b2 changed
    r = analyze(build(tmp_path))
    assert r["primary"]["H3"]["values"]["naive"] == pytest.approx((1.0 + 0.4) / 2)
    assert r["secondary"]["naive"]["adversarial_change_share"] == pytest.approx(0.7)


def test_mapping_error_output_maps_to_escalate(tmp_path):
    # @criterion C1
    for out in (
        {"decision": "refund", "parse_error": True},
        {"decision": "refund", "network_error": True},
        {"decision": "no_refund", "error": "timeout"},
        {"decision": None},
        {},
    ):
        assert ec.mapped(out) == "escalate"
    assert ec.mapped({"decision": "refund", "parse_error": False}) == "refund"
    # c1 (label escalate): one system run ends in a timeout with a stray decision; it maps to
    # escalate, so the case stays consistent and correct
    extra = {"system": {("c1", 3): {"decision": "refund", "error": "timeout"}}}
    r = analyze(build(tmp_path, extra=extra))
    assert r["primary"]["H1"]["values"]["system"] == 1.0
    assert r["primary"]["H2"]["values"]["system"] == 0.0
    assert r["errors"]["system"]["mapped_to_escalate"] == 1
    assert case_consistent([ec.mapped({"decision": "escalate"}), "escalate"])


def test_dot_or_exclusions_dot_case_alone(tmp_path):
    # @criterion C2
    r = analyze(build(tmp_path))
    # the pooled figures hold the six test cases only
    assert all(r["secondary"][a]["runs"] == 6 * R for a in AGENTS)
    assert r["cases"] == 6
    (dot,) = r["dot"]
    assert dot["case_id"] == "dot-p1" and dot["correct_answer"] == DOT_ANSWER
    assert dot["agents"]["system"]["correct"] == R
    assert dot["agents"]["naive"]["correct"] == 0
    assert dot["agents"]["cheap_strong"] == {
        "runs": R,
        "decisions": {"no_refund": 3, "refund": 7},
        "correct": 3,
        "correct_share": 0.3,
        "consistent": False,
    }
    # naive's DOT runs are all wrong, yet its pooled H2 is the one computed by hand
    assert r["primary"]["H2"]["values"]["naive"] == pytest.approx(1000 / 60)


def test_dot_or_exclusions_listed_with_counts(tmp_path):
    # @criterion C2
    unlabeled = case("u1", "DL", "2024-07-03")
    gap = case(
        "r1",
        "AA",
        "2026-07-03",
        "renumbered",
        facts={"renumbered": {"value": True, "constructed": False}},
    )
    adv = case("r2", "AA", "2026-07-04", "adversarial", clean_case_id="r1")
    later = case("r3", "AA", "2026-07-08", "renumbered")
    labels = LABEL | {"r1": "refund", "r2": "refund", "r3": "refund"}
    decisions = {
        a: d | {cid: ["refund"] * R for cid in ("u1", "r1", "r2", "r3")}
        for a, d in DECISIONS.items()
    }
    root = build(tmp_path, CASES + [unlabeled, gap, adv, later], labels, decisions)
    r = analyze(root)
    assert r["exclusions"] == {
        "unlabeled": {"count": 1, "ids": ["u1"]},
        "renumbered_gap": {"count": 1, "ids": ["r1"]},
        "adversarial_clean_excluded": {"count": 1, "ids": ["r2"]},
    }
    # r2 (its clean case r1 excluded) leaves H3 only; r3 flies after the gap: kept
    assert r["cases"] == 8
    assert all(r["secondary"][a]["runs"] == 8 * R for a in AGENTS)
    assert r["primary"]["H3"]["values"]["naive"] == pytest.approx(0.7)


def test_dot_or_exclusions_adversarial_with_excluded_clean_leaves_h3(tmp_path):
    # @criterion C2
    unlabeled = case("u1", "DL", "2024-08-03")
    adv = case("u2", "DL", "2024-08-04", "adversarial", clean_case_id="u1")
    labels = LABEL | {"u2": "refund"}
    decisions = {
        a: d | {"u1": ["refund"] * R, "u2": ["no_refund"] * R}
        for a, d in DECISIONS.items()
    }
    r = analyze(build(tmp_path, CASES + [unlabeled, adv], labels, decisions))
    assert r["exclusions"]["unlabeled"]["ids"] == ["u1"]
    assert r["exclusions"]["adversarial_clean_excluded"] == {"count": 1, "ids": ["u2"]}
    # u2 stays in H1 and H2 (its own runs: wrong for every agent), not in H3
    assert r["cases"] == 7
    assert r["primary"]["H3"]["values"]["naive"] == pytest.approx(0.7)
    assert r["primary"]["H2"]["values"]["system"] == pytest.approx(1000 / 70)


def test_render_page_and_json(tmp_path):
    # @criterion C8
    root = build(tmp_path)
    rc.main(["--root", str(root), "--runs-dir", str(root / "runs")])
    out = root / "runs/confirm"
    page = (out / "report.html").read_text()
    text = (out / "report.json").read_text()
    data = json.loads(text)
    for s in (page, text):
        assert "not confirmed" in s and "confirmed" in s
        assert "exploratory" not in s.lower()
        for v in (
            COMPLETE["date"],
            COMPLETE["tag"],
            COMPLETE["tag_commit"],
            COMPLETE["test_hash"],
            "fake-study-20261101",
        ):
            assert v in s
    assert "<strong>H3: confirmed</strong>" in page
    assert "<strong>H1: not confirmed</strong>" in page
    assert data["response_models"] == {
        "naive": {"fake-study-20261101": 2},
        "cheap_strong": {"fake-study-20261101": 3},
        "system": {"fake-study-20261101": 1, "none": 1},
    }
    assert data["development_grid"] == {
        "window": 0,
        "rows": [
            {"window": 0, "critical_errors": 20, "unnecessary_escalations": 50},
            {"window": 5, "critical_errors": 20, "unnecessary_escalations": 130},
        ],
    }
    assert "<td>5</td><td>20</td><td>130</td>" in page
    assert data["dot"][0]["correct_answer"] == DOT_ANSWER
    assert f"<strong>{DOT_ANSWER}</strong>" in page
    assert data["run"]["dollars"] == DOLLARS


def test_render_cost_view_and_latency(tmp_path):
    # @criterion C8
    r = analyze(build(tmp_path))
    sysv = r["cost_view"]["agents"]["system"]
    # 60 correct, 20 escalations (c1, c2), USD 0.25
    assert (sysv["correct"], sysv["escalations"]) == (60, 20)
    assert sysv["cost_per_correct_decision"] == pytest.approx(0.25 / 60)
    assert sysv["cost_per_correct_with_escalations"] == pytest.approx(40.25 / 60)
    assert r["accuracy_vs_dollars"][2] == {
        "agent": "system",
        "correct_share": 1.0,
        "dollars": 0.25,
    }
    # latency: every cost line (cache hit included) over the agent's 70 case-runs
    assert r["secondary"]["system"]["latency_per_answer"] == pytest.approx(4.0 / 70)
    assert r["secondary"]["cheap_strong"]["latency_per_answer"] == pytest.approx(6 / 70)
    assert set(r["by_airline"]["system"]) == {"AA", "DL"}
    assert r["by_airline"]["naive"]["AA"]["runs"] == 2 * R


def test_render_exit_2_without_complete_json(tmp_path, capsys):
    # @criterion C12
    root = build(tmp_path)
    (root / "runs/confirm/complete.json").unlink()
    with pytest.raises(SystemExit) as exit_:
        rc.main(["--root", str(root)])
    assert exit_.value.code == 2
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and "complete.json" in err[0]
    assert not (root / "runs/confirm/report.json").exists()


def test_render_incomplete_agent_marked_and_exit_1(tmp_path):
    # @criterion C12
    extra = {"naive": {("a2", 0): {"decision": "escalate", "network_error": True}}}
    root = build(tmp_path, extra=extra)
    with pytest.raises(SystemExit) as exit_:
        rc.main(["--root", str(root)])
    assert exit_.value.code == 1
    data = json.loads((root / "runs/confirm/report.json").read_text())
    assert data["incomplete"] == {"naive": 1}
    body = (root / "runs/confirm/report.html").read_text().split("<body>", 1)[1]
    assert body.startswith('<p class="notice">INCOMPLETE RUN: ')
    # the failed run counts as escalate: a2's label is no_refund, an unnecessary escalation
    assert data["secondary"]["naive"]["unnecessary_escalations"] == 1


def test_version_registered_and_corrected_side_by_side(tmp_path):
    clause = {"rule_version": "v1-260.2-cancelled"}
    extra = {"naive": {("a1", i): clause for i in range(3)}}
    root = build(tmp_path, extra=extra)
    rc.main(["--root", str(root), "--runs-dir", str(root / "runs")])
    out = root / "runs/confirm"
    data = json.loads((out / "report.json").read_text())
    page = (out / "report.html").read_text()
    naive = data["secondary"]["naive"]
    assert naive["version_errors_registered_per_100"] == pytest.approx(5.0)
    assert naive["version_errors_per_100"] == 0
    assert "registered" in page and "corrected" in page
    assert "prereg section 8" in page


def test_render_every_section6_metric_and_no_other_host(tmp_path):
    # @criterion C2
    root = build(tmp_path)
    rc.main(["--root", str(root), "--runs-dir", str(root / "runs")])
    page = (root / "runs/confirm/report.html").read_text()
    for needle in (
        "Primary hypotheses",
        "H2, each part apart",
        "95% interval",
        "Consistency share (H1) per agent",
        "Correct share",
        "Unnecessary escalations per 100 runs",
        "Version errors per 100 runs, registered",
        "Version errors per 100 runs, corrected",
        "Invented entitlements per 100 runs",
        "Policy leaks per 100 runs",
        "By case type",
        "By airline",
        "DOT guidance case",
        "Dollars per correct decision",
        "Latency per answer",
        "Cost view",
        "Trade-off curve",
        "Accuracy vs dollars",
        "Why the agents fail",
    ):
        assert needle in page, needle
    assert "src=" not in page and "<link" not in page and "http" not in page


# @criterion C10
def test_page_states_the_delay_limitation_with_the_sensitivity_figure(tmp_path):
    from eval import delays

    cases = [
        {**c, "facts": {"cancelled": {"value": False, "constructed": False}}}
        if c["case_id"] == "b1"
        else c
        for c in CASES
    ]
    root = build(tmp_path, cases=cases)
    rc.main(["--root", str(root), "--runs-dir", str(root / "runs")])
    page = (root / "runs/confirm/report.html").read_text()
    figures = delays.analyze(root, root / "runs")
    assert list(figures["flipped"]) == ["b1"]
    system = figures["agents"]["system"]["flipped"]
    assert system["critical"] == 10 and system["runs"] == 60
    para = page.split("<h2>Limitation: delays and the passenger who flew</h2><p>")[1]
    para = para.split("</p>")[0]
    assert "did not fly" in para
    assert "the system then makes 16.67 critical errors per 100 runs" in para
    assert f"{system['critical_per_100']:.2f}" == "16.67"
    assert "ADR-0008" in para
