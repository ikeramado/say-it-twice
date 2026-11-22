"""The operating point: chosen by a fixed rule on a re-scored cached run (C5)."""

import ast
import json
import shutil
from datetime import date
from pathlib import Path

from agents.system import engine, tools
from eval import operating_point as op

REPO = Path(__file__).resolve().parent.parent
PURCHASE = "2024-07-23"
# (case id, arrival delay, label): the DL rule v1 threshold is 120 minutes
CASES = [
    ("c-miss", 122, "escalate"),  # engine says refund; only a window of 2+ catches it
    (
        "c-near",
        112,
        "no_refund",
    ),  # 8 minutes off: a window of 10+ escalates it for nothing
    (
        "c-far",
        103,
        "no_refund",
    ),  # engine agrees; 17 off: only a window of 20 escalates
    ("c-clear", 30, "no_refund"),
]


def trace_line(case_id, delay):
    facts = {
        "cancelled": False,
        "arrival_delay_min": delay,
        "purchase_date": PURCHASE,
    }
    rule = tools.get_rule(date(2024, 7, 1), False)
    policy = tools.get_policy("DL", date.fromisoformat(PURCHASE))
    return {
        "id": case_id,
        "facts": facts,
        "rule_version": rule.id,
        "policy_versions": [policy.id],
        "engine": engine.decide(facts, rule, policy),
        "triggers": [],
    }


def make_root(tmp_path, runs=2):
    (tmp_path / "cases/dev").mkdir(parents=True)
    (tmp_path / "data/labels").mkdir(parents=True)
    d = tmp_path / "runs" / op.RUN
    (d / "outputs").mkdir(parents=True)
    (d / "traces").mkdir()
    (d / "costs.jsonl").write_text(json.dumps({"dollars": 1.25}) + "\n")
    (tmp_path / "docs/modules").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    shutil.copy(REPO / op.PREREG, tmp_path / op.PREREG)
    shutil.copy(REPO / op.TRIGGERS, tmp_path / op.TRIGGERS)
    cases, labels = [], []
    for cid, delay, lab in CASES:
        cases.append({"case_id": cid, "carrier": "DL"})
        labels.append({"case_id": cid, "decision": lab})
        for i in range(runs):
            name = f"{cid}_{i}.json"
            (d / "outputs" / name).write_text(json.dumps({"case_id": cid, "run": i}))
            (d / "traces" / name).write_text(json.dumps([trace_line(cid, delay)]))
    # a case whose flight was not found: the engine escalates, no trigger ran
    cases.append({"case_id": "c-none", "carrier": "DL"})
    labels.append({"case_id": "c-none", "decision": "escalate"})
    res = {"decision": "escalate", "clause": "no_flight"}
    (d / "outputs/c-none_0.json").write_text(
        json.dumps({"case_id": "c-none", "run": 0})
    )
    (d / "traces/c-none_0.json").write_text(
        json.dumps([{"id": "c-none", "engine": res, "triggers": []}])
    )
    (tmp_path / "cases/dev/cases.jsonl").write_text(
        "\n".join(json.dumps(c) for c in cases)
    )
    (tmp_path / op.LABELS).write_text("\n".join(json.dumps(x) for x in labels))
    return tmp_path


def test_choice_rule_known_answer():
    # @criterion C5
    grid = [
        {"window": 0, "critical_errors": 3, "unnecessary_escalations": 0},
        {"window": 5, "critical_errors": 1, "unnecessary_escalations": 9},
        {"window": 10, "critical_errors": 1, "unnecessary_escalations": 4},
        {"window": 15, "critical_errors": 1, "unnecessary_escalations": 4},
        {"window": 20, "critical_errors": 2, "unnecessary_escalations": 0},
    ]
    assert (
        op.choose(grid)["window"] == 10
    )  # fewest critical, then unnecessary, then smaller


def test_rescored_grid_and_choice(tmp_path):
    # @criterion C5
    grid = op.rescore(make_root(tmp_path))
    by = {
        r["window"]: (r["critical_errors"], r["unnecessary_escalations"]) for r in grid
    }
    # c-miss: 2 runs miss at window 0; c-near: 2 unnecessary from 10; c-far: from 20
    assert by == {0: (2, 0), 5: (0, 0), 10: (0, 2), 15: (0, 2), 20: (0, 4)}
    assert op.choose(grid)["window"] == 5


def test_rescoring_makes_no_model_call_no_call(tmp_path, monkeypatch):
    # @criterion C5
    import llm

    def boom(*a, **k):
        raise AssertionError("a model call")

    monkeypatch.setattr(llm.Gate, "call", boom)
    assert op.rescore(make_root(tmp_path))
    tree = ast.parse(Path(op.__file__).read_text())
    mods = {
        n.module if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    assert not {m for m in mods if m and m.split(".")[0] in ("llm", "runner")}


def test_write_is_recorded_and_matches_the_grid(tmp_path):
    # @criterion C5
    root = make_root(tmp_path)
    before = (root / op.PREREG).read_text()
    op.main(["--write", "--root", str(root)])
    window, in_yaml, rows = op.read_recorded(root)
    assert window == in_yaml == 5
    assert rows == op.rescore(root)
    text = (root / op.PREREG).read_text()
    assert "cost USD 1.2500" in text and "- **Operating point:** window=5 min" in text
    assert text.index("Operating point") < text.index("**Registration commit:**")
    assert before.count("**Registration commit:**") == text.count(
        "**Registration commit:**"
    )
    op.main(["--write", "--root", str(root)])  # a second write changes nothing
    assert (root / op.PREREG).read_text() == text
    assert "amount_threshold: null" in (root / op.TRIGGERS).read_text()
