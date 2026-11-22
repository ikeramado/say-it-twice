"""`make skeleton`: ingest (or reuse) one BTS month, build cases, run the placeholder agent
ten times per case through the gate, and write runs/<run_id>/report.html. No model call.

Entry: `python -m report.skeleton MONTH`.
"""

import html
import sys
from pathlib import Path

import runner
from cases.build_cases import build_cases
from eval.consistency import consistency_share, load_decisions
from ingest import pipeline

RUNS = 10
AGENT = "placeholder"


def render(agent, summary, run_id, month):
    pct = lambda x: f"{100 * x:.1f}%"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Consistency, walking skeleton</title></head>
<body>
<h1>Consistency of {html.escape(agent)}</h1>
<p id="share">Consistency share: <strong>{pct(summary["share"])}</strong>
({summary["consistent"]} of {summary["cases"]} cases give the same decision on all {RUNS} runs).</p>
<p id="interval">95% cluster-bootstrap interval by carrier-month:
[{pct(summary["low"])}, {pct(summary["high"])}]
({summary["clusters"]} carrier-months, {summary["resamples"]} resamples).</p>
<p>Month {html.escape(month)}, run {html.escape(run_id)}. Walking skeleton: a placeholder agent
with a fixed answer, no model call.</p>
</body></html>
"""


def skeleton(month, data_dir="data", runs_dir="runs", zip_path=None, run_id=None):
    data_dir, runs_dir = Path(data_dir), Path(runs_dir)
    run_id = run_id or f"skeleton-{month}"
    flights = data_dir / "clean" / "flights" / f"{month}.csv"
    if not flights.exists():
        ok, _, failures = pipeline.ingest(month, data_dir, zip_path)
        if not ok:
            raise RuntimeError("ingest quarantined: " + "; ".join(failures))
    cases = build_cases(flights)
    runner.run(AGENT, cases, RUNS, run_id, budget=1.0, ceiling=1.0, runs_dir=runs_dir)
    summary = consistency_share(cases, load_decisions(runs_dir / run_id))
    out = runs_dir / run_id / "report.html"
    out.write_text(render(AGENT, summary, run_id, month))
    return out, summary


def main(argv):
    if len(argv) != 2:
        print("usage: python -m report.skeleton YYYY-MM", file=sys.stderr)
        return 2
    out, s = skeleton(argv[1])
    print(f"{out}: share {s['share']:.3f} [{s['low']:.3f}, {s['high']:.3f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
