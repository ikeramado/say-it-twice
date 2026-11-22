"""eval/fixed_rule.py on fixture traces (card T64): the delay rule fixed to the law's words,
the 130 cases decided again from the traces with no model call."""

import json
from pathlib import Path

import pytest

from agents.system import engine, tools
from eval import fixed_rule
from tests.test_confirm_report import build, case

FIX = Path(__file__).parent / "fixtures" / "fixed_rule" / "traces.json"
TRACES = json.loads(FIX.read_text())
RUNS = 10


def facts(**kw):
    return {k: {"value": v, "constructed": False} for k, v in kw.items()}


def fcase(cid, **kw):
    return case(cid, "DL", "2025-12-01", "delay_above", facts=facts(**kw))


CASES = [
    fcase("d1", cancelled=False),
    fcase("d2", cancelled=False, travelled=False),
    fcase("c1", cancelled=True),
    fcase("e1", cancelled=False),
    fcase("n1", cancelled=False),
    case("m1", "DL", "2025-12-02", "missing_fact", facts={}),
]
LABEL = {
    "d1": "refund",
    "d2": "refund",
    "c1": "refund",
    "e1": "escalate",
    "n1": "no_refund",
    "m1": "escalate",
}
REGISTERED = {
    "d1": "refund",
    "d2": "refund",
    "c1": "refund",
    "e1": "escalate",
    "n1": "no_refund",
    "m1": "escalate",
}


@pytest.fixture
def root(tmp_path):
    decisions = {
        a: {c: [d] * RUNS for c, d in REGISTERED.items()}
        for a in ("naive", "cheap_strong", "system")
    }
    for a in decisions.values():
        a["dot-p1"] = ["no_refund"] * RUNS
    build(tmp_path, CASES, LABEL, decisions)
    tdir = tmp_path / "runs/confirm-system/traces"
    tdir.mkdir()
    for cid, line in TRACES.items():
        for i in range(RUNS):
            (tdir / f"{cid}_{i}.json").write_text(json.dumps([line]))
    return tmp_path


def test_no_travelled_fact_gives_no_refund_and_travelled_false_gives_a_refund(root):
    data = fixed_rule.analyze(root, root / "runs")
    assert (
        data["cases"]["d1"] == ["no_refund"] * RUNS
    )  # 200 min, the passenger may have flown
    assert data["cases"]["d2"] == ["refund"] * RUNS  # travelled: false


def test_a_cancellation_and_an_escalation_are_decided_as_registered(root):
    data = fixed_rule.analyze(root, root / "runs")
    assert data["cases"]["c1"] == ["refund"] * RUNS
    assert data["cases"]["e1"] == ["escalate"] * RUNS  # a trigger fired
    assert data["cases"]["n1"] == ["no_refund"] * RUNS
    assert (
        data["cases"]["m1"] == ["escalate"] * RUNS
    )  # no facts: registered decision kept


def test_the_figures_against_the_labels_as_adr_0008_reads_them(root):
    data = fixed_rule.analyze(root, root / "runs")
    assert data["total"] == 6 and data["consistent"] == 6
    # d1's refund label flips to no_refund: corrected, every case is right
    assert data["correct"] == 6
    assert data["registered"] == {"consistent": 6, "correct": 6, "correct_adr": 5}


def test_the_registered_engine_is_restored_and_reproduces_the_registered_decision(root):
    case_d1 = {"carrier": "DL", "facts": {}}
    line = TRACES["d1"]
    assert fixed_rule.decide(case_d1, {}, line, corrected=False) == "refund"
    assert fixed_rule.decide(case_d1, {}, line) == "no_refund"
    assert fixed_rule.decide(case_d1, {}, line, corrected=False) == "refund"
    assert engine._delay_path is not fixed_rule.fixed_delay_path


def test_an_airline_threshold_still_gives_the_refund(root):
    pol = tools.all_policy_versions("DL")[-1]
    line = {**TRACES["d1"], "policy_versions": [pol.id]}
    out = fixed_rule.decide({"carrier": "DL", "facts": {}}, {}, line)
    want = engine.decide(
        fixed_rule.rebuild({"carrier": "DL", "facts": {}}, line)[0],
        tools.get_rule(__import__("datetime").date(2025, 12, 1), False),
        pol,
    )["decision"]
    assert out == want


def test_no_model_or_provider_is_called(root, monkeypatch):
    from llm import provider

    def boom(*a, **k):
        raise AssertionError("a provider was called")

    for name in ("complete", "call", "client"):
        if hasattr(provider, name):
            monkeypatch.setattr(provider, name, boom)
    assert fixed_rule.analyze(root, root / "runs")["total"] == 6


def write_doc(root):
    doc = root / fixed_rule.DOC
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "# D\n\nProse.\n\n"
        + "".join(
            f"<!-- generated:{n} -->\nold\n<!-- /generated:{n} -->\n\n"
            for n in ("figures", "cases")
        )
    )
    return doc


# @criterion C10
def test_check_exits_1_on_a_stale_document_and_0_after_a_write(root, capsys):
    doc = write_doc(root)
    args = ["--root", str(root), "--runs-dir", str(root / "runs")]
    assert fixed_rule.main([*args, "--check"]) == 1
    assert doc.read_text().count("old") == 2
    assert fixed_rule.main(args) == 0
    text = doc.read_text()
    assert "| Corrected, ADR-0008 labels | 6 of 6 | 6 of 6 |" in text
    assert "| d1 | refund |" not in text and "| d1 | no_refund |" in text
    assert fixed_rule.main([*args, "--check"]) == 0
    doc.write_text(text.replace("6 of 6", "5 of 6", 1))
    assert fixed_rule.main([*args, "--check"]) == 1
    assert "differ from a rerun" in capsys.readouterr().err


def test_the_real_document_holds_both_figures_and_the_ten_decisions_of_test_bnd_001():
    repo = Path(__file__).resolve().parent.parent
    text = (repo / fixed_rule.DOC).read_text()
    data = fixed_rule.analyze(repo, repo / "runs")
    assert "exploratory" in text.lower()
    r, n = data["registered"], data["total"]
    assert (
        f"| Registered, frozen labels | {r['consistent']} of {n} | {r['correct']} of {n} |"
        in text
    )
    assert (
        f"| Corrected, ADR-0008 labels | {data['consistent']} of {n} | {data['correct']} of {n} |"
        in text
    )
    ten = " ".join(data["cases"]["test-bnd-001"])
    assert f"| test-bnd-001 | no_refund | {ten} |" in text
