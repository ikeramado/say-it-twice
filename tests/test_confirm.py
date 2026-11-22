"""`make confirm` and `make confirm-exploratory` (prereg section 3, C12), on a temporary git
repository with a fake registration tag, fake test cases and a fake provider: no real tag, no
real model call."""

import csv
import json
import subprocess

import pytest
import yaml

import runner
from cases import split
from llm import provider as providers
from tests.test_agent_view import FLIGHT, a_case
from tests.test_cost_gate import connection_error

ANSWER = {
    "decision": "refund",
    "clause": "AA-2024-04-12-x",
    "rule_version": "v1",
    "policy_version": "AA-2024-04-12",
    "explanation": "Your flight was significantly delayed.",
}
PRICE = {"input": 1.0, "cache_write": 1.25, "cached_input": 0.1, "output": 1.0}
MODELS = {"agents": "fake-study", "exploratory": "fake-large", "models": {}}
DOT = {
    "case_id": "dot-guidance-p1",
    "carrier": None,
    "flight_number": None,
    "flight_date": None,
    "bts_flight": None,
    "facts": {"event": {"from": "dot", "value": "cancellation"}},
    "message": "The airline cancelled the flight and offered nothing; a refund is owed.",
    "type": "dot_example",
    "hypothetical": True,
}
GIT = [
    "git",
    "-c",
    "user.name=test",
    "-c",
    "user.email=test@example.com",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "tag.gpgsign=false",
    "-c",
    "core.hooksPath=/dev/null",
]


class Fake:
    """A provider that answers every call, or fails on the network (5 attempts: the call and
    the gate's 4 retries) just before the answers numbered in `cut`."""

    def __init__(self, cut=()):
        self.cut, self.calls, self.ok, self.failing, self.models = set(cut), 0, 0, 0, []

    def __call__(self, model, prompt, max_output, prefix=None):
        self.calls += 1
        self.models.append(model)
        if not self.failing and self.ok in self.cut:
            self.cut.discard(self.ok)
            self.failing = 5
        if self.failing:
            self.failing -= 1
            raise connection_error()
        self.ok += 1
        return json.dumps(ANSWER), 100, 0, 20, "end_turn", "served-model-1"


def git(root, *args):
    subprocess.run([*GIT, "-C", str(root), *args], check=True, capture_output=True)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def jsonl(cases):
    return "".join(json.dumps(c, sort_keys=True) + "\n" for c in cases)


TESTS = [
    a_case(case_id="test-pol-001"),
    a_case(
        case_id="test-pol-002",
        message={"text": "Late again, I want my money.", "constructed": True},
    ),
]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A registered repository: test cases, hash.txt, the prereg hash, tag prereg-v1; and
    a data root with the one flight the test cases name."""
    d = tmp_path / "data" / "clean" / "flights"
    d.mkdir(parents=True)
    with (d / "2024-09.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(FLIGHT))
        w.writeheader()
        w.writerow(FLIGHT)
    monkeypatch.setenv("SAY_IT_TWICE_DATA_ROOT", str(tmp_path))
    root = tmp_path / "repo"
    digest = split.test_hash(TESTS)
    write(root / "config/models.yaml", yaml.safe_dump(MODELS))
    write(
        root / "config/prices.yaml",
        yaml.safe_dump({"fake-study": PRICE, "fake-large": PRICE}),
    )
    write(root / "cases/test/cases.jsonl", jsonl(TESTS))
    write(root / "cases/test/dot/cases.jsonl", jsonl([DOT]))
    write(root / "cases/test/hash.txt", digest + "\n")
    write(root / "docs/modules/prereg.md", f"- **Test case hash:** {digest}\n")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "registration")
    git(root, "tag", "prereg-v1")
    return root


def confirm(root, provider, **kw):
    return runner.confirm(
        root, 10.0, 10.0, provider=provider, workers=1, sleep=lambda s: None, **kw
    )


def outputs(run_dir):
    return {
        f.name: json.loads(f.read_text()) for f in (run_dir / "outputs").glob("*.json")
    }


def _no_tag(root):
    git(root, "tag", "-d", "prereg-v1")


def _changed_case(root):
    write(root / "cases/test/cases.jsonl", jsonl([TESTS[0], a_case(case_id="test-x")]))


def _hash_txt(root):
    write(root / "cases/test/hash.txt", "0" * 64 + "\n")


def _prereg_at_tag(root):
    # The prereg at the tag registered another hash; the working tree's copy is right.
    good = (root / "docs/modules/prereg.md").read_text()
    git(root, "tag", "-d", "prereg-v1")
    write(root / "docs/modules/prereg.md", f"- **Test case hash:** {'1' * 64}\n")
    git(root, "commit", "-q", "-am", "another hash")
    git(root, "tag", "prereg-v1")
    write(root / "docs/modules/prereg.md", good)


def _complete(root):
    write(root / "runs/confirm/complete.json", "{}\n")


@pytest.mark.parametrize(
    "spoil", [_no_tag, _changed_case, _hash_txt, _prereg_at_tag, _complete]
)
def test_confirm_refuses_before_any_call(repo, spoil):
    # @criterion C12
    spoil(repo)
    fake = Fake()
    with pytest.raises(runner.Refused):
        confirm(repo, fake)
    assert fake.calls == 0
    assert not list((repo / "runs").glob("confirm-*"))


def test_confirm_refuses_second_run(repo, monkeypatch, capsys):
    # @criterion C12
    first = confirm(repo, Fake())
    assert first["complete"] and (repo / "runs/confirm/complete.json").exists()
    called = []
    monkeypatch.setattr(providers, "real_provider", lambda *a, **k: called.append(a))
    monkeypatch.setattr(runner, "ROOT", repo)
    with pytest.raises(SystemExit) as exit_:
        runner.main(["confirm", "--budget", "10", "--ceiling", "10"])
    assert exit_.value.code == 2 and called == []
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and "runs once" in err[0]


def test_confirm_runs_every_test_case_and_resumes(repo):
    # @criterion C12
    # Real calls: naive 20, cheap_strong 100 (its own samples, none the naive
    # agent's, so all are real calls), system 20: cut two of the
    # system's.
    cut = Fake(cut={122, 127})
    res = confirm(repo, cut)
    runs = repo / "runs"
    assert not res["complete"] and not (runs / "confirm/complete.json").exists()
    assert res["network_failures"] == {"naive": 0, "cheap_strong": 0, "system": 2}
    system = outputs(runs / "confirm-system")
    assert sum(o["network_error"] for o in system.values()) == 2
    for agent in runner.STUDY_AGENTS:
        outs = outputs(runs / f"confirm-{agent}")
        ids = {o["case_id"] for o in outs.values()}
        assert ids == {"test-pol-001", "test-pol-002", "dot-guidance-p1"}
        assert len(outs) == 3 * runner.CONFIRM_RUNS
        assert not any("exploratory" in o for o in outs.values())
    assert set(cut.models) == {"fake-study"}
    # the same command calls only the two case-runs the network cut, then completes
    again = Fake()
    res = confirm(repo, again)
    assert again.calls == 2 and res["complete"]
    done = json.loads((runs / "confirm/complete.json").read_text())
    assert done["test_hash"] == split.test_hash(TESTS)
    assert done["model"] == "fake-study"
    assert done["tag_commit"] == subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "prereg-v1^{commit}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert set(done["dollars"]) == set(runner.STUDY_AGENTS) and done["date"]
    assert not any(o["network_error"] for o in outputs(runs / "confirm-system").values())


def test_exploratory_refuses_before_confirm_is_complete(repo):
    # @criterion C12
    fake = Fake()
    with pytest.raises(runner.Refused, match="not complete"):
        runner.confirm_exploratory(repo, 10.0, 10.0, provider=fake, workers=1)
    assert fake.calls == 0


def test_exploratory_refuses_without_entry(repo):
    # @criterion C12
    confirm(repo, Fake())
    write(repo / "config/models.yaml", yaml.safe_dump({"agents": "fake-study"}))
    fake = Fake()
    with pytest.raises(runner.Refused, match="exploratory"):
        runner.confirm_exploratory(repo, 10.0, 10.0, provider=fake, workers=1)
    assert fake.calls == 0


def test_exploratory_runs_naive_with_its_entry_and_marks_outputs(repo):
    # @criterion C12
    confirm(repo, Fake())
    before = {p.name for p in (repo / "runs").iterdir()}
    for _ in range(2):  # exploratory: it may run again
        fake = Fake()
        res = runner.confirm_exploratory(repo, 10.0, 10.0, provider=fake, workers=1)
        assert res["run_id"] == "exploratory-naive-fake-large"
        assert set(fake.models) <= {"fake-large"}
    assert {p.name for p in (repo / "runs").iterdir()} - before == {
        "exploratory-naive-fake-large"
    }
    d = repo / "runs/exploratory-naive-fake-large"
    outs = outputs(d)
    assert len(outs) == 3 * runner.CONFIRM_RUNS
    assert all(o["exploratory"] is True for o in outs.values())
    lines = [json.loads(x) for x in (d / "costs.jsonl").read_text().splitlines()]
    assert lines and {x["model"] for x in lines} == {"fake-large"}
