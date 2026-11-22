"""`make dev-eval`: the three agents over the development subset through the runner and the
gate, then every metric of the prereg's section 6 apart from the confirmatory ones.

Entry: `python -m report.dev_eval --subset FILE --runs N --agents a,b --budget D --ceiling D
[--protocol NAME]`. Writes runs/<protocol>/report.json and report.html, then exits 1 when an
agent's run is invalid (more than half its answers unreadable, eval.metrics.invalid) or
incomplete (a case-run failed on the network after the gate's retries; a rerun completes it
from the cache).
"""

import argparse
import html
import json
from pathlib import Path

import runner
from eval.metrics import evaluate

PROTOCOL = "dev-subset"
ROWS = (
    ("Consistency share", "consistency_share", "pct"),
    ("Wrong decisions per 100 runs", "wrong_decisions_per_100", "num"),
    ("Missed escalations per 100 runs", "missed_escalations_per_100", "num"),
    ("Needed escalations per 100 runs", "needed_escalations_per_100", "num"),
    ("Unnecessary escalations per 100 runs", "unnecessary_escalations_per_100", "num"),
    ("Correct share", "correct_share", "pct"),
    ("Version errors per 100 runs", "version_errors_per_100", "num"),
    ("Invented entitlements per 100 runs", "invented_entitlements_per_100", "num"),
    ("Policy leaks per 100 runs", "policy_leaks_per_100", "num"),
    ("Adversarial change share", "adversarial_change_share", "pct"),
    ("Parse errors per 100 runs", "parse_errors_per_100", "num"),
    ("Dollars", "dollars", "usd"),
    ("Dollars per correct decision", "cost_per_correct_decision", "usd"),
    ("Latency per answer (s)", "latency_per_answer", "num"),
)


def fmt(x, kind):
    if x is None:
        return "n/a"
    return {"pct": f"{100 * x:.1f}%", "usd": f"${x:.4f}"}.get(kind, f"{x:.2f}")


def table(title, blocks):
    names = list(blocks)
    head = "".join(f"<th>{html.escape(n)}</th>" for n in names)
    body = "".join(
        f"<tr><td>{label}</td>"
        + "".join(f"<td>{fmt(blocks[n][key], kind)}</td>" for n in names)
        + "</tr>"
        for label, key, kind in ROWS
    )
    return f"<h2>{html.escape(title)}</h2><table><tr><th></th>{head}</tr>{body}</table>"


def invalid_notice(report):
    """The first paragraph of the page when the run is invalid for some agent, else ''."""
    bad = report.get("invalid") or []
    if not bad:
        return ""
    named = ", ".join(
        f"{html.escape(a)} (${report['invalid_dollars'][a]:.4f})" for a in bad
    )
    return (
        f"<p>INVALID RUN: more than half the answers could not be read for {named}; "
        "no metric is reported for them.</p>"
    )


def incomplete_notice(report):
    """A paragraph naming the agents with network failures, else ''."""
    gone = report.get("incomplete") or {}
    if not gone:
        return ""
    named = ", ".join(f"{html.escape(a)} ({n})" for a, n in sorted(gone.items()))
    return (
        f"<p>INCOMPLETE RUN: case-runs failed on the network for {named}; no metric is "
        "reported for them. Run it again: the cache keeps every answer already read.</p>"
    )


def render(report):
    # No agent with metrics (all invalid or incomplete): no empty table.
    parts = (
        [
            table(
                "All cases, per agent",
                {a: m["overall"] for a, m in report["agents"].items()},
            )
        ]
        if report["agents"]
        else []
    )
    types = sorted({t for m in report["agents"].values() for t in m["by_type"]})
    for t in types:
        parts.append(
            table(
                f"Case type {t}",
                {
                    a: m["by_type"][t]
                    for a, m in report["agents"].items()
                    if t in m["by_type"]
                },
            )
        )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        "<title>Development evaluation</title></head><body>"
        f"{incomplete_notice(report)}{invalid_notice(report)}<h1>Development evaluation: {html.escape(report['protocol'])}</h1>"
        f"<p>Total dollars: ${report['total_dollars']:.4f}. Development cases only; "
        "no confirmatory metric.</p>" + "".join(parts) + "</body></html>\n"
    )


def dev_eval(
    root,
    agents,
    runs,
    subset=None,
    protocol=PROTOCOL,
    budget=0.0,
    ceiling=0.0,
    prices=None,
    provider=None,
    workers=runner.DEFAULT_WORKERS,
    sleep=None,
):
    """Run the agents, evaluate, write report.json and report.html; returns (path, dollars)."""
    root = Path(root)
    runs_dir = root / "runs"
    cases = runner.load_dev_cases(root, subset)
    runner.run_study(
        agents,
        cases,
        runs,
        protocol,
        budget,
        ceiling,
        runs_dir,
        prices,
        provider,
        workers,
        sleep,
    )
    report = evaluate(root, protocol, agents, runs_dir)
    out = runs_dir / protocol
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    (out / "report.html").write_text(render(report))
    return out / "report.json", report["total_dollars"]


def main(argv=None, provider=None, sleep=None):
    """provider, sleep: the seams a test passes down to runner.run_study (None: the real
    provider, time.sleep)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--agents", default=",".join(runner.STUDY_AGENTS))
    ap.add_argument("--budget", type=float, required=True)
    ap.add_argument("--ceiling", type=float, required=True)
    ap.add_argument("--protocol", default=PROTOCOL)
    ap.add_argument("--workers", type=int, default=runner.DEFAULT_WORKERS)
    a = ap.parse_args(argv)
    try:
        path, total = dev_eval(
            runner.ROOT,
            a.agents.split(","),
            a.runs,
            a.subset,
            a.protocol,
            a.budget,
            a.ceiling,
            provider=provider,
            workers=a.workers,
            sleep=sleep,
        )
    except runner.MissingKey as err:
        raise SystemExit(f"dev-eval: {err}; export it in your own terminal") from None
    print(f"report: {path}")
    print(f"total dollars: {total:.4f}")
    report = json.loads(Path(path).read_text())
    bad = report.get("invalid") or []
    gone = report.get("incomplete") or {}
    if gone:
        named = ", ".join(f"{a} ({n})" for a, n in sorted(gone.items()))
        print(f"INCOMPLETE RUN: network failures for {named}; run it again")
    if bad:
        print(
            f"INVALID RUN: more than half the answers unreadable for {', '.join(bad)}"
        )
    if bad or gone:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
