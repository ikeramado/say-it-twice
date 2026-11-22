"""Runs cases x runs x agent through the gate; writes under runs/<run_id>/.

Entries: `python -m runner estimate|run --agent placeholder --cases N --runs N`,
`python -m runner estimate --protocol dev-subset|dev-full|confirm|all` (the study's protocols,
costed with caching, no call), `python -m runner smoke --model <entry>` (one tiny real call),
and `python -m runner confirm|confirm-exploratory --budget D --ceiling D` (prereg section 3:
the test cases, once, after the registration tag; then the exploratory run). Only the confirm
and exploratory paths load test cases.
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from agents import AGENTS
from cases.split import test_hash
from llm import (
    PROFILES,
    BudgetExceeded,
    CeilingReached,
    Gate,
    estimate_protocols,
    estimate_run,
    is_network_error,
    load_prices,
)
from llm.provider import MissingKey, agent_model, load_models

RUNS_DIR = Path("runs")
ROOT = Path(__file__).resolve().parent
SMOKE_CEILING = 0.05
SMOKE_PROMPT = "Reply with the single word: ok"


def synthetic_cases(n):
    return [
        {
            "case_id": f"case-{i:03d}",
            "carrier": "XX",
            "flight_number": str(100 + i),
            "flight_date": "2024-07-01",
            "origin": "JFK",
            "type": "cancelled",
            "facts": {"cancelled": {"value": True, "constructed": False}},
            "message": {
                "text": f"My flight {i} was cancelled, I want my money back.",
                "constructed": True,
            },
        }
        for i in range(n)
    ]


def estimate(agent_name, cases, runs, prices=None, model=None):
    """model: the entry to cost the run with instead of the agent's MODEL."""
    agent = AGENTS[agent_name]
    prices = prices or load_prices()
    return estimate_run(
        [agent.prompt(c) for c in cases],
        runs,
        agent.CALLS_PER_CASE,
        model or agent.MODEL,
        prices,
    )


def _lines(path):
    path = Path(path)
    return (
        sum(1 for line in path.read_text().splitlines() if line.strip())
        if path.exists()
        else 0
    )


def protocols(root=ROOT):
    """Case-runs of the three protocols of docs/plan.md."""
    return {
        "dev-subset": 40 * 3,
        "dev-full": _lines(root / "cases/dev/cases.jsonl") * 10,
        "confirm": (
            _lines(root / "cases/test/cases.jsonl")
            + _lines(root / "cases/test/dot/cases.jsonl")
        )
        * 10,
    }


def prefix_tokens(root=ROOT):
    """The rule and policy texts, the cached prefix of every call, as characters / 4."""
    texts = [
        root / "rules/versions.yaml",
        *sorted((root / "rules/policies").glob("*.yaml")),
    ]
    return sum(len(p.read_text()) for p in texts) // 4


def estimate_study(protocol="all", model=None, prices=None, root=ROOT):
    """{(agent, protocol): estimate} for the agents' model of config/models.yaml."""
    prices = prices or load_prices()
    model = model or agent_model()
    chosen = protocols(root)
    if protocol != "all":
        chosen = {protocol: chosen[protocol]}
    return estimate_protocols(chosen, prefix_tokens(root), prices[model])


def smoke(model, runs_dir=RUNS_DIR, prices=None, provider=None):
    """One tiny call through the gate (ceiling USD 0.05), then the same call again, which the
    response cache answers. Returns the two cost lines."""
    prices = prices or load_prices()
    gate = Gate(
        Path(runs_dir) / "smoke",
        model,
        prices,
        SMOKE_CEILING,
        Path(runs_dir) / "cache",
        provider=provider,
        max_output=16,
    )
    before = gate.costs.read_text().splitlines() if gate.costs.exists() else []
    gate.call(SMOKE_PROMPT, 0)
    gate.call(SMOKE_PROMPT, 0)
    return [json.loads(x) for x in gate.costs.read_text().splitlines()[len(before) :]]


def _cost_lines(path):
    if not Path(path).exists():
        return []
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


DEFAULT_WORKERS = 16
STUDY_AGENTS = ("naive", "cheap_strong", "system")


def load_dev_cases(root=ROOT, subset=None):
    """The development cases, or those whose ids are listed (one per line) in `subset`."""
    root = Path(root)
    cases = [
        json.loads(x)
        for x in (root / "cases/dev/cases.jsonl").read_text().splitlines()
        if x.strip()
    ]
    if subset is None:
        return cases
    ids = {x.strip() for x in Path(subset).read_text().splitlines() if x.strip()}
    return [c for c in cases if c["case_id"] in ids]


def run_study(
    agents,
    cases,
    runs,
    protocol,
    budget,
    ceiling,
    runs_dir=RUNS_DIR,
    prices=None,
    provider=None,
    workers=DEFAULT_WORKERS,
    sleep=None,
    model=None,
):
    """Each agent over the cases under its own run_id `<protocol>-<agent>`; the dollars of
    each, in order. The ceiling covers every run together (the gate seeds it from all costs).
    model: the entry every agent's gate calls instead of the agent's MODEL."""
    return {
        a: run(
            a,
            cases,
            runs,
            f"{protocol}-{a}",
            budget,
            ceiling,
            runs_dir=runs_dir,
            prices=prices,
            provider=provider,
            sleep=sleep,
            workers=workers,
            model=model,
        )
        for a in agents
    }


def run(
    agent_name,
    cases,
    runs,
    run_id,
    budget,
    ceiling,
    runs_dir=RUNS_DIR,
    prices=None,
    provider=None,
    sleep=None,
    workers=DEFAULT_WORKERS,
    model=None,
    exploratory=False,
):
    """model: the entry the gate calls and the estimate costs, instead of the agent's MODEL
    (the agent calls whatever gate it is given). exploratory: each output carries
    `"exploratory": true`."""
    agent = AGENTS[agent_name]
    prices = prices or load_prices()
    runs_dir = Path(runs_dir)
    kw = {"sleep": sleep} if sleep else {}
    gate = Gate(
        runs_dir / run_id,
        model or agent.MODEL,
        prices,
        ceiling,
        runs_dir / "cache",
        provider=provider,
        budget=budget,
        **kw,
    )
    gate.check_budget(estimate(agent_name, cases, runs, prices, model), budget)
    out = runs_dir / run_id
    for sub in ("outputs", "traces"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    def case_run(case, i):
        bound = gate.for_sample(i)
        try:
            res = agent.run(case, bound)
        except Exception as exc:
            if not is_network_error(exc):
                raise
            # The network failed after the gate's retries: a failed output, no trace, and
            # nothing cached (the gate caches only answers), so a rerun repeats this one.
            res = {"decision": "escalate", "explanation": "", "network_error": True}
        spent = bound.cost_lines
        name = f"{case['case_id']}_{i}.json"
        mark = {"exploratory": True} if exploratory else {}
        (out / "outputs" / name).write_text(
            json.dumps(
                {
                    **mark,
                    "case_id": case["case_id"],
                    "run": i,
                    "decision": res["decision"],
                    "explanation": res["explanation"],
                    "clause": res.get("clause"),
                    "rule_version": res.get("rule_version"),
                    "policy_version": res.get("policy_version"),
                    "parse_error": bool(res.get("parse_error")),
                    "network_error": bool(res.get("network_error")),
                    "dollars": sum(x["dollars"] for x in spent),
                    "calls": len(spent),
                    "cache_hits": sum(1 for x in spent if x["cache"]),
                    "latency": sum(x["latency"] for x in spent if not x["cache"]),
                }
            )
        )
        if "trace" in res:
            (out / "traces" / name).write_text(json.dumps(res["trace"]))

    stop = None
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(case_run, c, i) for c in cases for i in range(runs)]
        for f in as_completed(futures):
            if f.cancelled():
                continue
            exc = f.exception()
            if exc is None:
                continue
            if stop is None or (
                isinstance(exc, (BudgetExceeded, CeilingReached))
                and not isinstance(stop, (BudgetExceeded, CeilingReached))
            ):
                stop = exc
            # Queued case-runs are cancelled; the ones in flight finish.
            for g in futures:
                g.cancel()
    if stop is not None:
        raise stop
    return gate.run_total()


def network_failures(run_dir):
    """Outputs of a run recorded as failed on a network error (a rerun completes them)."""
    d = Path(run_dir) / "outputs"
    if not d.exists():
        return 0
    return sum(
        1 for f in d.glob("*.json") if json.loads(f.read_text()).get("network_error")
    )


# ---- the confirmatory run (prereg section 3) and the exploratory run after it ----

TAG = "prereg-v1"
CONFIRM = "confirm"
CONFIRM_RUNS = 10
PREREG = "docs/modules/prereg.md"
PREREG_HASH = re.compile(r"\*\*Test case hash:\*\* *([0-9a-f]{64})")


class Refused(Exception):
    """The confirm or exploratory run may not start; nothing was called (the CLI exits 2)."""


def _jsonl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def load_test_cases(root):
    """The test cases (hashed) and the DOT subset (run with them, not hashed): only the
    confirm and exploratory paths call this."""
    root = Path(root)
    tests = _jsonl(root / "cases/test/cases.jsonl")
    dot = root / "cases/test/dot/cases.jsonl"
    return tests, (_jsonl(dot) if dot.exists() else [])


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


def registered(root, tag=TAG):
    """(test hash, the tag's commit, cases) once every precondition but complete.json holds:
    the tag exists, and the test cases' hash equals cases/test/hash.txt and the prereg's
    "Test case hash" as it is at the tag. Raises Refused otherwise."""
    root = Path(root)
    tagged = _git(root, "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}")
    if tagged.returncode != 0:
        raise Refused(f"no registration tag {tag}: register first (prereg section 3)")
    commit = tagged.stdout.strip()
    tests, dot = load_test_cases(root)
    digest = test_hash(tests)
    saved = (root / "cases/test/hash.txt").read_text().strip()
    if digest != saved:
        raise Refused(
            f"the test cases hash to {digest}, cases/test/hash.txt holds {saved}"
        )
    shown = _git(root, "show", f"{tag}:{PREREG}")
    m = PREREG_HASH.search(shown.stdout) if shown.returncode == 0 else None
    if m is None:
        raise Refused(f"{PREREG} at {tag} has no test case hash")
    if m.group(1) != digest:
        raise Refused(
            f"the test cases hash to {digest}, {PREREG} at {tag} registered {m.group(1)}"
        )
    return digest, commit, tests + dot


def _models(root):
    return load_models(Path(root) / "config/models.yaml")


def _prices(root):
    return load_prices(Path(root) / "config/prices.yaml")


def confirm(
    root,
    budget,
    ceiling,
    *,
    provider=None,
    runs_dir=None,
    tag=TAG,
    workers=DEFAULT_WORKERS,
    sleep=None,
):
    """The three study agents on every test case, CONFIRM_RUNS runs each, into
    runs/confirm-<agent>/. Refuses (Refused) before any call when a precondition fails or
    runs/confirm/complete.json exists. A run cut by the network or the cost gate writes no
    complete.json, and the same call resumes it from the cache. Returns
    {"complete", "dollars", "network_failures"}."""
    root = Path(root)
    runs_dir = Path(runs_dir) if runs_dir is not None else root / "runs"
    done = runs_dir / CONFIRM / "complete.json"
    if done.exists():
        raise Refused(f"the confirmatory run is complete ({done}); it runs once")
    digest, commit, cases = registered(root, tag)
    model = agent_model(_models(root))
    dollars = run_study(
        STUDY_AGENTS,
        cases,
        CONFIRM_RUNS,
        CONFIRM,
        budget,
        ceiling,
        runs_dir=runs_dir,
        prices=_prices(root),
        provider=provider,
        workers=workers,
        sleep=sleep,
        model=model,
    )
    failed = {a: network_failures(runs_dir / f"{CONFIRM}-{a}") for a in STUDY_AGENTS}
    complete = not any(failed.values())
    if complete:
        done.parent.mkdir(parents=True, exist_ok=True)
        done.write_text(
            json.dumps(
                {
                    "date": datetime.date.today().isoformat(),
                    "test_hash": digest,
                    "model": model,
                    "tag": tag,
                    "tag_commit": commit,
                    "dollars": dollars,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    return {"complete": complete, "dollars": dollars, "network_failures": failed}


def confirm_exploratory(
    root,
    budget,
    ceiling,
    *,
    provider=None,
    runs_dir=None,
    tag=TAG,
    workers=DEFAULT_WORKERS,
    sleep=None,
):
    """The naive agent with the `exploratory` entry of config/models.yaml on the same test
    cases, CONFIRM_RUNS runs, into runs/exploratory-naive-<entry>/, each output marked
    exploratory. Only after runs/confirm/complete.json; it may run again."""
    root = Path(root)
    runs_dir = Path(runs_dir) if runs_dir is not None else root / "runs"
    if not (runs_dir / CONFIRM / "complete.json").exists():
        raise Refused("the confirmatory run is not complete: run make confirm first")
    model = _models(root).get("exploratory")
    if not model:
        raise Refused("config/models.yaml has no `exploratory` entry")
    _, _, cases = registered(root, tag)
    run_id = f"exploratory-naive-{model}"
    total = run(
        "naive",
        cases,
        CONFIRM_RUNS,
        run_id,
        budget,
        ceiling,
        runs_dir=runs_dir,
        prices=_prices(root),
        provider=provider,
        sleep=sleep,
        workers=workers,
        model=model,
        exploratory=True,
    )
    return {
        "dollars": {"naive": total},
        "network_failures": {"naive": network_failures(runs_dir / run_id)},
        "run_id": run_id,
    }


def _confirm_cli(command, a, sleep):
    fn = confirm if command == "confirm" else confirm_exploratory
    try:
        res = fn(ROOT, a.budget, a.ceiling, workers=a.workers, sleep=sleep)
    except Refused as err:
        print(f"{command}: refused: {err}", file=sys.stderr)
        raise SystemExit(2) from None
    except MissingKey as err:
        raise SystemExit(f"{command}: {err}; export it in your own terminal") from None
    failed = 0
    for name, d in res["dollars"].items():
        n = res["network_failures"][name]
        failed += n
        print(f"{name}: total dollars {d:.4f}, network failures {n}")
    if failed:
        print(
            f"INCOMPLETE RUN: {failed} case-runs failed on the network; "
            "run the same command again, the cache keeps the rest"
        )
        raise SystemExit(1)
    if command == "confirm":
        print("confirmatory run complete: runs/confirm/complete.json")


def main(argv=None, sleep=None):
    """sleep: the gate's wait between retries (None: time.sleep), a test's seam."""
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "command",
        choices=["estimate", "run", "smoke", "confirm", "confirm-exploratory"],
    )
    ap.add_argument("--agent", default="placeholder")
    ap.add_argument("--cases", type=int)
    ap.add_argument("--runs", type=int)
    ap.add_argument("--protocol", default=None)
    ap.add_argument("--subset")
    ap.add_argument("--agents", default=",".join(STUDY_AGENTS))
    ap.add_argument("--model")
    ap.add_argument("--budget", type=float, default=0.0)
    ap.add_argument("--ceiling", type=float, default=0.0)
    ap.add_argument("--run-id", default="run")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    a = ap.parse_args(argv)
    if a.command in ("confirm", "confirm-exploratory"):
        _confirm_cli(a.command, a, sleep)
        return
    if a.command == "smoke":
        if not a.model:
            ap.error("smoke needs --model <entry of config/models.yaml>")
        try:
            lines = smoke(a.model)
        except MissingKey as err:
            raise SystemExit(f"smoke: {err}; export it in your own terminal") from None
        for line in lines:
            print(
                f"model {line['model']}: {line['input_tokens']} input "
                f"({line['cached_tokens']} cached), {line['output_tokens']} output, "
                f"${line['dollars']:.6f}" + (", cache hit" if line["cache"] else "")
            )
        return
    if a.command == "estimate" and a.protocol:
        if a.protocol not in ("all", "dev-subset", "dev-full", "confirm"):
            ap.error("--protocol must be all, dev-subset, dev-full or confirm")
        model = a.model or agent_model()
        print(f"model {model}, prefix {prefix_tokens()} tokens, with prompt caching")
        print(
            "agent         protocol    calls   input_tokens  cached_tokens  dollars  batch"
        )
        total = 0.0
        for (agent, name), e in estimate_study(a.protocol, model).items():
            total += e["dollars"]
            print(
                f"{agent:<13} {name:<10} {e['calls']:>6} {e['input_tokens']:>14} "
                f"{e['cached_tokens']:>14} {e['dollars']:>8.4f} {e['batch_dollars']:>6.4f}"
            )
        print(f"total dollars: {total:.4f} ({len(PROFILES)} agents)")
        return
    if a.command == "run" and a.cases is None:
        cases = load_dev_cases(ROOT, a.subset)
        totals = run_study(
            a.agents.split(","),
            cases,
            a.runs or 3,
            a.protocol or "dev-subset",
            a.budget,
            a.ceiling,
            workers=a.workers,
            sleep=sleep,
        )
        failed = 0
        for name, d in totals.items():
            n = network_failures(RUNS_DIR / f"{a.protocol or 'dev-subset'}-{name}")
            failed += n
            print(f"{name}: total dollars {d:.4f}, network failures {n}")
        if failed:
            print(
                f"INCOMPLETE RUN: {failed} case-runs failed on the network; "
                "run it again, the cache keeps the rest"
            )
            raise SystemExit(1)
        return
    if a.cases is None or a.runs is None:
        ap.error("--cases and --runs are required")
    cases = synthetic_cases(a.cases)
    if a.command == "estimate":
        e = estimate(a.agent, cases, a.runs)
        print(f"calls: {e['calls']}")
        print(f"tokens: {e['input_tokens']} input, {e['output_tokens']} output")
        print(f"dollars: {e['dollars']:.4f}")
    else:
        total = run(
            a.agent,
            cases,
            a.runs,
            a.run_id,
            a.budget,
            a.ceiling,
            sleep=sleep,
            workers=a.workers,
        )
        print(f"total dollars: {total:.4f}")
        failed = network_failures(RUNS_DIR / a.run_id)
        if failed:
            print(f"INCOMPLETE RUN: {failed} case-runs failed on the network")
            raise SystemExit(1)


if __name__ == "__main__":
    main()
