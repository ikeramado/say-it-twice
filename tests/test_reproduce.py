"""`make reproduce` (C12): every report rebuilt from cached runs of a fixture tree, the same
bytes on a second run, and any provider call inside it raises."""

import json
import os
import subprocess
from pathlib import Path

import pytest

import runner
from llm import Gate, load_prices
from llm import provider as providers
from report import reproduce
from tests import test_confirm_report as tc

REPO = Path(__file__).resolve().parent.parent
DEV = [
    tc.case("d1", "DL", "2024-09-01"),
    tc.case("d2", "AA", "2024-09-02", "adversarial", clean_case_id="d1"),
]
REPORTS = (
    "confirm/report.json",
    "confirm/report.html",
    "dev-subset/report.json",
    "dev-subset/report.html",
    "dev-full/report.json",
    "dev-full/report.html",
)


def tree(tmp_path):
    root = tc.build(tmp_path)
    tc.jsonl(root / "cases/dev/cases.jsonl", DEV)
    labels = root / "data/labels/labels.jsonl"
    labels.write_text(
        labels.read_text()
        + "".join(
            json.dumps(
                {"case_id": c["case_id"], "decision": "refund", "rule_version": "v1"}
            )
            + "\n"
            for c in DEV
        )
    )
    runs_dir = root / "runs"
    for a in ("naive", "system"):
        d = runs_dir / f"dev-subset-{a}"
        (d / "outputs").mkdir(parents=True)
        for c in DEV:
            for i in range(3):
                (d / "outputs" / f"{c['case_id']}_{i}.json").write_text(
                    json.dumps(
                        {"case_id": c["case_id"], "run": i, "decision": "refund"}
                    )
                )
        (d / "costs.jsonl").write_text('{"dollars": 0.01, "latency": 0.5}\n')
    d = runs_dir / "dev-full-system"
    for sub in ("outputs", "traces"):
        (d / sub).mkdir(parents=True)
    for c in DEV:
        name = f"{c['case_id']}_0.json"
        (d / "outputs" / name).write_text(
            json.dumps({"case_id": c["case_id"], "run": 0, "decision": "refund"})
        )
        # no flight in the trace: the engine's decision stands, no trigger is re-run
        (d / "traces" / name).write_text(
            json.dumps([{"engine": {"decision": "refund"}}])
        )
    return root


def make(root):
    env = {k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MFLAGS")}
    env["UV_OFFLINE"] = "1"
    return subprocess.run(
        [
            "make",
            "-s",
            "-C",
            str(REPO),
            "reproduce",
            f"RUNS_DIR={root / 'runs'}",
            f"ROOT_DIR={root}",
            f"ENV_FILE={root / 'no.env'}",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=300,
    )


def test_make_reproduce_writes_the_same_reports_twice(tmp_path):
    # @criterion C12
    root = tree(tmp_path)
    first = make(root)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "provider: report.reproduce.refuse (raises)" in first.stdout
    assert "operating point: window=0 min" in first.stdout
    written = {p: (root / "runs" / p).read_bytes() for p in REPORTS}
    assert all(written.values())
    assert json.loads(written["confirm/report.json"])["primary"]["H3"]["verdict"]
    second = make(root)
    assert second.returncode == 0, second.stdout + second.stderr
    assert {p: (root / "runs" / p).read_bytes() for p in REPORTS} == written


def test_reproduce_installs_the_raising_provider(tmp_path):
    # @criterion C12
    with reproduce.no_provider() as installed:
        assert installed is reproduce.refuse
        assert providers.get_provider("placeholder") is reproduce.refuse
        assert providers.get_provider("claude-haiku-5-5") is reproduce.refuse
        assert providers.real_provider is reproduce.refuse
        gate = Gate(
            tmp_path / "run", "placeholder", load_prices(), 1.0, tmp_path / "cache"
        )
        assert gate.provider is reproduce.refuse
        with pytest.raises(reproduce.ProviderCalled):
            gate.call("hello", 0)
    assert providers.get_provider("placeholder") is providers.placeholder
    assert providers.real_provider is not reproduce.refuse


def test_reproduce_fails_on_a_step_that_calls_a_model(tmp_path, monkeypatch):
    # @criterion C12
    root = tree(tmp_path)

    def calls_a_model(root, runs_dir):
        runner.run("placeholder", DEV, 1, "would-call", 1.0, 1.0, runs_dir=runs_dir)

    monkeypatch.setattr(reproduce, "dev_reports", calls_a_model)
    with pytest.raises(reproduce.ProviderCalled):
        reproduce.reproduce(root, root / "runs")


def test_reproduce_skips_reports_without_runs(tmp_path, capsys):
    # @criterion C12
    (tmp_path / "runs").mkdir()
    assert reproduce.reproduce(tmp_path, tmp_path / "runs") == 0
    out = capsys.readouterr().out
    assert "skipped report-confirm" in out and "skipped dev-subset" in out
    assert "skipped the operating-point grid" in out
