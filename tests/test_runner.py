import json
import time

import runner


def test_two_cases_ten_runs(tmp_path):
    # @criterion C9
    cases = runner.synthetic_cases(2)
    total = runner.run(
        "placeholder", cases, 10, "r1", budget=1.0, ceiling=1.0, runs_dir=tmp_path
    )
    d = tmp_path / "r1"
    assert total == 0
    assert len(list((d / "outputs").iterdir())) == 20
    assert len(list((d / "traces").iterdir())) == 20
    lines = [json.loads(x) for x in (d / "costs.jsonl").read_text().splitlines()]
    assert len(lines) == 20
    assert {
        "model",
        "input_tokens",
        "cached_tokens",
        "output_tokens",
        "dollars",
        "latency",
    } <= set(lines[0])
    out = json.loads(next((d / "outputs").iterdir()).read_text())
    assert out["decision"] in {"refund", "no_refund", "escalate"}


def _fake(delay):
    def prov(model, prompt, max_output, prefix=None):
        time.sleep(delay)
        return "no_refund", len(prompt) // 4 + 1, 0, 5

    return prov


def _snapshot(d):
    out = {}
    for sub in ("outputs", "traces"):
        for f in sorted((d / sub).iterdir()):
            data = json.loads(f.read_text())
            if sub == "outputs":
                data.pop("latency")
            out[f"{sub}/{f.name}"] = data
    return out


def test_parallel_matches_sequential(tmp_path):
    # @criterion C9
    cases = runner.synthetic_cases(64)
    t = {}
    for name, workers in (("seq", 1), ("par", 16)):
        start = time.monotonic()
        runner.run(
            "placeholder",
            cases,
            1,
            name,
            budget=1.0,
            ceiling=1.0,
            runs_dir=tmp_path / name,
            provider=_fake(0.05),
            workers=workers,
        )
        t[name] = time.monotonic() - start
    assert t["par"] < t["seq"] / 4
    assert _snapshot(tmp_path / "seq" / "seq") == _snapshot(tmp_path / "par" / "par")


def test_per_output_attribution_concurrent(tmp_path):
    # @criterion C9
    runner.run(
        "placeholder",
        runner.synthetic_cases(12),
        3,
        "r",
        budget=1.0,
        ceiling=1.0,
        runs_dir=tmp_path,
        provider=_fake(0.01),
        workers=8,
    )
    d = tmp_path / "r"
    outs = [json.loads(f.read_text()) for f in (d / "outputs").iterdir()]
    lines = [json.loads(x) for x in (d / "costs.jsonl").read_text().splitlines()]
    assert len(outs) == 36 and len(lines) == 36
    assert all(o["calls"] == 1 and o["cache_hits"] == 0 for o in outs)
    assert sum(o["dollars"] for o in outs) == sum(x["dollars"] for x in lines)
    # a second run reads every answer from the cache: hits equal calls, no dollars
    runner.run(
        "placeholder",
        runner.synthetic_cases(12),
        3,
        "r2",
        budget=1.0,
        ceiling=1.0,
        runs_dir=tmp_path,
        provider=_fake(0.01),
        workers=8,
    )
    outs = [json.loads(f.read_text()) for f in (tmp_path / "r2" / "outputs").iterdir()]
    assert all(o["cache_hits"] == o["calls"] == 1 for o in outs)


def _heavy(model, prompt, max_output, prefix=None):
    return "no_refund", 1, 0, max_output


PRICED = {"placeholder": {"input": 0.0, "cached_input": 0.0, "output": 1000.0}}


def test_stop_raises_budget_or_ceiling_and_keeps_outputs(tmp_path):
    # @criterion C9
    import pytest

    from llm import BudgetExceeded, CeilingReached

    cases = runner.synthetic_cases(20)  # worst case 0.3 per call, 6.0 projected
    # a run already holding 0.5 dollars, a budget just above the projection
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "costs.jsonl").write_text(json.dumps({"dollars": 0.5}) + "\n")
    with pytest.raises(BudgetExceeded):
        runner.run(
            "placeholder",
            cases,
            1,
            "b",
            budget=6.3,
            ceiling=100.0,
            runs_dir=tmp_path,
            prices=PRICED,
            provider=_heavy,
            workers=4,
        )
    written = list((tmp_path / "b" / "outputs").iterdir())
    assert 0 < len(written) < 20
    with pytest.raises(CeilingReached):
        runner.run(
            "placeholder",
            cases,
            1,
            "c",
            budget=100.0,
            ceiling=1.0,
            runs_dir=tmp_path,
            prices=PRICED,
            provider=_heavy,
            workers=4,
        )
    written = list((tmp_path / "c" / "outputs").iterdir())
    assert 0 < len(written) < 20


def _cut(prompts_down, calls):
    """A provider whose network is down for the prompts holding one of `prompts_down`."""
    from tests.test_cost_gate import connection_error

    lock = __import__("threading").Lock()

    def prov(model, prompt, max_output, prefix=None):
        with lock:
            calls.append(prompt)
        if any(p in prompt for p in prompts_down):
            raise connection_error()
        return "no_refund", len(prompt) // 4 + 1, 0, 5

    return prov


def test_network_failures_do_not_stop_the_run(tmp_path):
    # @criterion C9
    cases = runner.synthetic_cases(40)
    down = [f"My flight {i} was" for i in (3, 17, 31)]
    calls, sleeps = [], []
    total = runner.run(
        "placeholder",
        cases,
        1,
        "r",
        budget=1.0,
        ceiling=1.0,
        runs_dir=tmp_path,
        provider=_cut(down, calls),
        sleep=sleeps.append,
        workers=16,
    )
    assert total == 0
    d = tmp_path / "r"
    outs = {f.name: json.loads(f.read_text()) for f in (d / "outputs").iterdir()}
    assert len(outs) == 40
    failed = {n for n, o in outs.items() if o["network_error"]}
    assert failed == {"case-003_0.json", "case-017_0.json", "case-031_0.json"}
    for n in failed:
        o = outs[n]
        assert o["decision"] == "escalate" and o["explanation"] == ""
        assert o["clause"] is None and o["rule_version"] is None
        assert o["policy_version"] is None and o["parse_error"] is False
        assert o["calls"] == 0 and o["dollars"] == 0 and o["cache_hits"] == 0
        assert not (d / "traces" / n).exists()
    assert all(not o["network_error"] for n, o in outs.items() if n not in failed)
    assert len(list((d / "traces").iterdir())) == 37
    assert len(calls) == 37 + 3 * 5 and sleeps == [2, 4, 8, 16] * 3
    assert runner.network_failures(d) == 3
    # a rerun with a healthy network calls only the three that failed
    calls.clear()
    runner.run(
        "placeholder",
        cases,
        1,
        "r",
        budget=1.0,
        ceiling=1.0,
        runs_dir=tmp_path,
        provider=_cut([], calls),
        sleep=sleeps.append,
        workers=16,
    )
    assert len(calls) == 3
    assert sorted(next(p for p in down if p in c) for c in calls) == sorted(down)
    assert runner.network_failures(d) == 0
    assert len(list((d / "traces").iterdir())) == 40


def test_runner_cli_exits_1_on_network_failures(tmp_path, monkeypatch, capsys):
    # @criterion C9
    import pytest

    from tests.test_cost_gate import connection_error

    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path)
    real_run = runner.run

    def run_cut(*a, **kw):
        kw["provider"] = lambda *x, **y: (_ for _ in ()).throw(connection_error())
        kw["runs_dir"] = tmp_path
        return real_run(*a, **kw)

    monkeypatch.setattr(runner, "run", run_cut)
    sleeps = []
    with pytest.raises(SystemExit) as exit_:
        runner.main(
            ["run", "--cases", "2", "--runs", "1", "--budget", "1", "--ceiling", "1"],
            sleep=sleeps.append,
        )
    assert exit_.value.code == 1
    assert "INCOMPLETE RUN: 2 case-runs" in capsys.readouterr().out
    assert sleeps == [2, 4, 8, 16] * 2


def test_dev_entries_never_test_cases(tmp_path, monkeypatch):
    # @criterion C12
    from pathlib import Path

    import pytest

    from report import dev_eval

    def jsonl(ids):
        return "".join(json.dumps({"case_id": i}) + "\n" for i in ids)

    (tmp_path / "cases/dev").mkdir(parents=True)
    (tmp_path / "cases/test/dot").mkdir(parents=True)
    (tmp_path / "cases/dev/cases.jsonl").write_text(jsonl(["dev-a-001", "dev-a-002"]))
    (tmp_path / "cases/dev/subset.txt").write_text("dev-a-002\n")
    (tmp_path / "cases/test/cases.jsonl").write_text(jsonl(["test-a-001"]))
    (tmp_path / "cases/test/dot/cases.jsonl").write_text(jsonl(["dot-a"]))

    class Stop(Exception):
        pass

    seen, read = [], []

    def study(agents, cases, *a, **kw):
        seen.append([c["case_id"] for c in cases])
        raise Stop

    real_read = Path.read_text

    def read_text(self, *a, **kw):
        read.append(str(self))
        return real_read(self, *a, **kw)

    def no_test_cases(*a, **kw):
        raise AssertionError("a development entry loaded the test cases")

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "run_study", study)
    monkeypatch.setattr(runner, "load_test_cases", no_test_cases)
    monkeypatch.setattr(Path, "read_text", read_text)
    money = ["--budget", "1", "--ceiling", "1"]
    # make dev-full
    with pytest.raises(Stop):
        runner.main(["run", "--runs", "10", "--protocol", "dev-full", *money])
    # make dev-eval
    with pytest.raises(Stop):
        dev_eval.main(["--subset", str(tmp_path / "cases/dev/subset.txt"), *money])
    assert seen == [["dev-a-001", "dev-a-002"], ["dev-a-002"]]
    assert not [p for p in read if "cases/test" in p]
