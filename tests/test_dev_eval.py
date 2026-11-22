import csv
import json
import shutil
from pathlib import Path

import pytest

import runner
from eval.metrics import invalid
from report.dev_eval import dev_eval, main
from tests import test_agent_view as tv

REPO = Path(__file__).resolve().parent.parent
KEYS = {
    "consistency_share",
    "wrong_decisions_per_100",
    "missed_escalations_per_100",
    "needed_escalations_per_100",
    "unnecessary_escalations_per_100",
    "version_errors_per_100",
    "invented_entitlements_per_100",
    "policy_leaks_per_100",
    "adversarial_change_share",
    "parse_errors_per_100",
    "cost_per_correct_decision",
    "latency_per_answer",
}


def make_tree(tmp_path):
    cases = [
        {
            "case_id": f"c{i}",
            "carrier": "DL",
            "flight_number": str(100 + i),
            "flight_date": "2024-07-01",
            "origin": "ATL",
            "type": "adversarial" if i == 2 else "cancelled",
            "facts": {"cancelled": {"value": True, "constructed": False}},
            "message": {"text": "Cancelled, refund please.", "constructed": True},
            **({"clean_case_id": "c1", "attack": "x"} if i == 2 else {}),
        }
        for i in range(3)
    ]
    (tmp_path / "cases/dev").mkdir(parents=True)
    (tmp_path / "cases/dev/cases.jsonl").write_text(
        "\n".join(json.dumps(c) for c in cases)
    )
    (tmp_path / "cases/dev/subset.txt").write_text("c0\nc1\nc2\n")
    (tmp_path / "data/labels").mkdir(parents=True)
    (tmp_path / "data/labels/labels.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "case_id": f"c{i}",
                    "decision": "refund",
                    "clause": "v1-42305-refund",
                    "rule_version": "v1",
                    "policy_version": "DL-2024-03-12",
                }
            )
            for i in range(3)
        )
    )
    (tmp_path / "rules").mkdir()
    shutil.copy(REPO / "rules/versions.yaml", tmp_path / "rules/versions.yaml")
    return tmp_path


def test_placeholder_report_with_every_key_and_no_model_call(tmp_path):
    # @criterion C8
    root = make_tree(tmp_path)

    path, total = dev_eval(
        root,
        ["placeholder"],
        3,
        subset=root / "cases/dev/subset.txt",
        budget=1.0,
        ceiling=1.0,
    )
    report = json.loads(Path(path).read_text())
    assert total == 0
    block = report["agents"]["placeholder"]["overall"]
    assert KEYS <= set(block)
    assert block["runs"] == 9
    assert "cancelled" in report["agents"]["placeholder"]["by_type"]
    assert (path.parent / "report.html").exists()
    assert (root / "runs/dev-subset-placeholder/costs.jsonl").exists()
    # latency per answer: every cost line's latency (cache hits included) over the 9 runs
    lines = (root / "runs/dev-subset-placeholder/costs.jsonl").read_text().splitlines()
    seconds = sum(json.loads(x)["latency"] for x in lines)
    assert block["latency_per_answer"] == pytest.approx(seconds / 9)
    out = json.loads(
        next((root / "runs/dev-subset-placeholder/outputs").iterdir()).read_text()
    )
    assert {"clause", "rule_version", "policy_version", "parse_error"} <= set(out)


def test_only_eval_reads_the_labels():
    # @criterion C4
    for f in [REPO / "runner.py", *(REPO / "report").glob("*.py")]:
        assert "labels" not in f.read_text(encoding="utf-8").lower(), f


def test_invalid_run_reported_and_exits_1(tmp_path, monkeypatch):
    # @criterion C2
    # More than half the naive answers unreadable (the failed run of 2026-11-19): the run is
    # invalid for naive, its metrics are left out, its dollars kept, and the entry exits 1.
    root = make_tree(tmp_path)
    d = root / "data/clean/flights"
    d.mkdir(parents=True)
    with (d / "2024-07.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(tv.FLIGHT))
        w.writeheader()
        for i in range(3):
            w.writerow(
                {
                    **tv.FLIGHT,
                    "carrier": "DL",
                    "flight_number": str(100 + i),
                    "date": "2024-07-01",
                    "origin": "ATL",
                    "cancelled": "1",
                }
            )
    monkeypatch.setenv("SAY_IT_TWICE_DATA_ROOT", str(root))
    monkeypatch.setattr(runner, "ROOT", root)

    def provider(model, prompt, max_output, prefix=None):
        if model == "placeholder":
            return "refund", 10, 0, 1, "end_turn"
        return "", 100, 0, max_output, "max_tokens"

    with pytest.raises(SystemExit) as exit_:
        main(
            [
                "--subset",
                str(root / "cases/dev/subset.txt"),
                "--runs",
                "1",
                "--agents",
                "naive,placeholder",
                "--budget",
                "1",
                "--ceiling",
                "1",
            ],
            provider=provider,
        )
    assert exit_.value.code == 1
    out = root / "runs/dev-subset"
    report = json.loads((out / "report.json").read_text())
    assert report["invalid"] == ["naive"]
    assert set(report["agents"]) == {"placeholder"}
    spent = sum(
        json.loads(x)["dollars"]
        for x in (root / "runs/dev-subset-naive/costs.jsonl").read_text().splitlines()
    )
    assert spent > 0 and report["invalid_dollars"] == {"naive": spent}
    assert report["total_dollars"] == pytest.approx(
        spent + report["agents"]["placeholder"]["overall"]["dollars"]
    )
    page = (out / "report.html").read_text()
    body = page.split("<body>", 1)[1]
    assert body.startswith("<p>INVALID RUN: ") and f"naive (${spent:.4f})" in body
    assert "placeholder (" not in body.split("</p>", 1)[0]


def test_invalid_is_strictly_more_than_half():
    # @criterion C2
    def outs(bad, good):
        return [{"parse_error": True}] * bad + [{"parse_error": False}] * good

    assert not invalid(outs(1, 1)) and invalid(outs(2, 1)) and not invalid([])
    # only the output's own field counts, not its decision or explanation
    assert not invalid([{"decision": "escalate", "parse_error": False}] * 3)


def test_incomplete_on_network_failures(tmp_path, monkeypatch):
    # @criterion C9
    # A network cut that outlasts the gate's retries for one case: the run goes on, the agent
    # is reported incomplete with no metric, the entry exits 1; a rerun completes it.
    from tests.test_cost_gate import connection_error

    root = make_tree(tmp_path)
    monkeypatch.setattr(runner, "ROOT", root)
    cut = {"on": True}

    def provider(model, prompt, max_output, prefix=None):
        if cut["on"] and "DL101" in prompt:
            raise connection_error()
        return "refund", 10, 0, 1, "end_turn"

    argv = [
        "--subset",
        str(root / "cases/dev/subset.txt"),
        "--runs",
        "2",
        "--agents",
        "placeholder",
        "--budget",
        "1",
        "--ceiling",
        "1",
    ]
    sleeps = []
    with pytest.raises(SystemExit) as exit_:
        main(argv, provider=provider, sleep=sleeps.append)
    assert exit_.value.code == 1
    assert sleeps == [2, 4, 8, 16] * 2
    out = root / "runs/dev-subset"
    report = json.loads((out / "report.json").read_text())
    assert report["incomplete"] == {"placeholder": 2}
    assert report["agents"] == {} and report["invalid"] == []
    body = (out / "report.html").read_text().split("<body>", 1)[1]
    assert body.startswith("<p>INCOMPLETE RUN: ") and "placeholder (2)" in body
    assert "Consistency share" not in body and "<th>placeholder</th>" not in body
    # network failures are not parse errors
    outs = [
        json.loads(f.read_text())
        for f in (root / "runs/dev-subset-placeholder/outputs").iterdir()
    ]
    assert sum(o["network_error"] for o in outs) == 2
    assert not any(o["parse_error"] for o in outs)
    assert not invalid(outs + [{"parse_error": True}])
    # the network is back: the rerun completes the agent and reports its metrics
    cut["on"] = False
    main(argv, provider=provider, sleep=sleeps.append)
    report = json.loads((out / "report.json").read_text())
    assert report["incomplete"] == {}
    assert report["agents"]["placeholder"]["overall"]["runs"] == 6
