"""`make report-confirm`: the confirmatory report (prereg sections 1, 5 and 6), from the cached
runs/confirm-<agent>/ with no model call.

Entry: `python -m report.confirm [--root DIR] [--runs-dir DIR]`. Writes
runs/confirm/report.json and report.html. Exits 2 with one line when runs/confirm/complete.json
is missing (or an agent's run is), 1 when an agent's run is incomplete (network failures) or
invalid (more than half its answers unreadable): the report is still written, the agent
marked at the top.
"""

import argparse
import html
import json
import sys
from pathlib import Path

import runner
from eval import delays as delay_reading
from eval.confirm import RUN, NotComplete, analyze

SECONDARY = (
    ("Correct share", "correct_share", "pct"),
    ("Consistency share", "consistency_share", "pct"),
    ("Critical errors per 100 runs", "critical_errors_per_100", "num"),
    ("Wrong decisions per 100 runs", "wrong_decisions_per_100", "num"),
    ("Missed escalations per 100 runs", "missed_escalations_per_100", "num"),
    ("Needed escalations per 100 runs", "needed_escalations_per_100", "num"),
    ("Unnecessary escalations per 100 runs", "unnecessary_escalations_per_100", "num"),
    (
        "Version errors per 100 runs, registered",
        "version_errors_registered_per_100",
        "num",
    ),
    ("Version errors per 100 runs, corrected", "version_errors_per_100", "num"),
    ("Invented entitlements per 100 runs", "invented_entitlements_per_100", "num"),
    ("Policy leaks per 100 runs", "policy_leaks_per_100", "num"),
    ("Adversarial change share", "adversarial_change_share", "pct"),
    ("Parse errors per 100 runs", "parse_errors_per_100", "num"),
    ("Runs", "runs", "int"),
    ("Dollars", "dollars", "usd"),
    ("Dollars per correct decision", "cost_per_correct_decision", "usd"),
    ("Latency per answer (s)", "latency_per_answer", "num"),
)
SHORT = SECONDARY[
    :14
]  # by case type and by airline: no dollars or latency of their own

STYLE = (
    "body{font-family:system-ui,sans-serif;max-width:72rem;margin:1rem auto;"
    "padding:0 16px;color:#1a1a1a;background:#fff}"
    "table{border-collapse:collapse;margin:.5rem 0 1.5rem;display:block;overflow-x:auto}"
    "th,td{border:1px solid #ccc;padding:.25rem .5rem;text-align:right}"
    "th:first-child,td:first-child{text-align:left}"
    ".notice{border:2px solid #b00;padding:.5rem}"
)


def fmt(x, kind="num"):
    if x is None:
        return "n/a"
    if kind == "pct":
        return f"{100 * x:.1f}%"
    if kind == "usd":
        return f"${x:.4f}"
    if kind == "int":
        return str(x)
    if kind == "diff_pct":
        return f"{100 * x:+.1f} pts"
    if kind == "diff":
        return f"{x:+.2f}"
    return f"{x:.2f}"


def esc(x):
    return html.escape(str(x))


def grid(head, rows):
    h = "".join(f"<th>{esc(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{h}</tr>{b}</table>"


def agent_table(blocks, rows):
    names = list(blocks)
    return grid(
        ["", *names],
        [
            [esc(label), *(fmt(blocks[n].get(key), kind) for n in names)]
            for label, key, kind in rows
        ],
    )


def notices(report):
    out = []
    if report["incomplete"]:
        named = ", ".join(
            f"{esc(a)} ({n})" for a, n in sorted(report["incomplete"].items())
        )
        out.append(
            f'<p class="notice">INCOMPLETE RUN: case-runs failed on the network for '
            f"{named}; they count as escalate (prereg section 6, missing data).</p>"
        )
    if report["invalid"]:
        out.append(
            '<p class="notice">INVALID RUN: more than half the answers could not be read '
            f"for {esc(', '.join(report['invalid']))}.</p>"
        )
    return "".join(out)


def primary_section(report):
    rows = []
    for h, p in report["primary"].items():
        kind = "pct" if h in ("H1", "H3") else "num"
        dkind = "diff_pct" if kind == "pct" else "diff"
        for c in p["comparisons"]:
            rows.append(
                [
                    esc(h),
                    esc(p["name"]),
                    f"system {fmt(p['values']['system'], kind)}",
                    f"{esc(c['other'])} {fmt(p['values'][c['other']], kind)}",
                    fmt(c["difference"], dkind),
                    f"[{fmt(c['low'], dkind)}, {fmt(c['high'], dkind)}]",
                    "yes" if c["meets_criterion"] else "no",
                    f"<strong>{esc(p['verdict'])}</strong>",
                ]
            )
        if not p["comparisons"]:
            rows.append(
                [esc(h), esc(p["name"]), "", "", "n/a", "n/a", "no", esc(p["verdict"])]
            )
    h2 = report["primary"]["H2"]
    apart = grid(
        ["", *report["agents"]],
        [
            [
                "Wrong decisions per 100 runs",
                *(fmt(h2["wrong_decisions_per_100"][a]) for a in report["agents"]),
            ],
            [
                "Missed escalations per 100 runs",
                *(fmt(h2["missed_escalations_per_100"][a]) for a in report["agents"]),
            ],
        ],
    )
    verdicts = "".join(
        f"<li><strong>{esc(h)}: {esc(p['verdict'])}</strong> ({esc(p['criterion'])})</li>"
        for h, p in report["primary"].items()
    )
    return (
        "<h2>Primary hypotheses</h2>"
        f"<ul>{verdicts}</ul>"
        + grid(
            [
                "",
                "Metric",
                "System",
                "Other agent",
                "Difference (system minus other)",
                "95% interval",
                "Interval meets the criterion",
                "Hypothesis verdict",
            ],
            rows,
        )
        + f"<p>Paired cluster bootstrap by carrier-month, {report['resamples']} resamples, "
        f"seed {report['seed']}, 95% percentile intervals; the same clusters serve every "
        "agent in a resample. Confirmed and not confirmed results are shown alike.</p>"
        "<h3>H2, each part apart</h3>" + apart
    )


def cost_section(report):
    cv = report["cost_view"]
    rows = [
        [
            esc(a),
            fmt(v["dollars"], "usd"),
            str(v["correct"]),
            str(v["escalations"]),
            fmt(v["cost_per_correct_decision"], "usd"),
            fmt(v["cost_per_correct_with_escalations"], "usd"),
        ]
        for a, v in cv["agents"].items()
    ]
    acc = [
        [esc(r["agent"]), fmt(r["correct_share"], "pct"), fmt(r["dollars"], "usd")]
        for r in report["accuracy_vs_dollars"]
    ]
    return (
        f"<h2>Cost view (an escalation costs ${cv['escalation_cost']:.2f})</h2>"
        + grid(
            [
                "Agent",
                "Dollars",
                "Correct decisions",
                "Escalations",
                "Dollars per correct decision",
                "With escalations",
            ],
            rows,
        )
        + "<h2>Accuracy vs dollars</h2>"
        + grid(["Agent", "Correct share", "Dollars"], acc)
    )


def by_section(title, blocks, report):
    keys = sorted({k for a in report["agents"] for k in blocks[a]})
    parts = [f"<h2>{esc(title)}</h2>"]
    for k in keys:
        parts.append(f"<h3>{esc(k)}</h3>")
        parts.append(
            agent_table(
                {a: blocks[a][k] for a in report["agents"] if k in blocks[a]}, SHORT
            )
        )
    return "".join(parts)


def dot_section(report):
    if not report["dot"]:
        return "<h2>DOT guidance case, reported alone</h2><p>No DOT case.</p>"
    parts = ["<h2>DOT guidance case, reported alone (never pooled)</h2>"]
    for d in report["dot"]:
        parts.append(
            f"<p>{esc(d['case_id'])}: correct answer (the DOT text's own reading) "
            f"<strong>{esc(d['correct_answer'])}</strong>.</p>"
        )
        parts.append(
            grid(
                ["Agent", "Runs", "Decisions", "Correct", "Same decision every run"],
                [
                    [
                        esc(a),
                        str(v["runs"]),
                        esc(", ".join(f"{k} {n}" for k, n in v["decisions"].items())),
                        f"{v['correct']} ({fmt(v['correct_share'], 'pct')})",
                        "yes" if v["consistent"] else "no",
                    ]
                    for a, v in d["agents"].items()
                ],
            )
        )
    return "".join(parts)


def exclusions_section(report):
    names = {
        "unlabeled": "Unresolved labeling disagreement",
        "renumbered_gap": "Renumbered, flying 2026-07-01 to 2026-07-06",
        "adversarial_clean_excluded": "Adversarial cases left out of H3 (clean case excluded)",
    }
    return "<h2>Exclusions (prereg section 6)</h2>" + grid(
        ["Reason", "Count", "Case ids"],
        [
            [esc(names[k]), str(v["count"]), esc(", ".join(v["ids"]) or "none")]
            for k, v in report["exclusions"].items()
        ],
    )


def errors_section(report):
    return "<h2>Errors mapped to escalate</h2>" + grid(
        ["Agent", "Network errors", "Parse errors", "Mapped to escalate"],
        [
            [
                esc(a),
                str(v["network_errors"]),
                str(v["parse_errors"]),
                str(v["mapped_to_escalate"]),
            ]
            for a, v in report["errors"].items()
        ],
    )


def models_section(report):
    rows = [
        [esc(a), esc(m), str(n)]
        for a, counts in report["response_models"].items()
        for m, n in counts.items()
    ]
    return "<h2>Response models (from the cost lines)</h2>" + grid(
        ["Agent", "Response model", "Calls"], rows
    )


def grid_section(report):
    g = report["development_grid"]
    rows = [
        [str(r["window"]), str(r["critical_errors"]), str(r["unnecessary_escalations"])]
        for r in g["rows"]
    ]
    return (
        "<h2>Trade-off curve: development operating-point grid (descriptive)</h2>"
        f"<p>System, full development set, prereg section 7; frozen window: "
        f"{esc(g['window'])} min.</p>"
        + grid(["Window (min)", "Critical errors", "Unnecessary escalations"], rows)
    )


def consistency_section(report):
    rows = []
    for a in report["agents"]:
        c = report["secondary"][a]["consistency"]
        rows.append(
            [
                esc(a),
                fmt(c["share"], "pct"),
                f"[{fmt(c['low'], 'pct')}, {fmt(c['high'], 'pct')}]",
                f"{c['consistent']} of {c['cases']}",
            ]
        )
    return "<h2>Consistency share (H1) per agent, with 95% interval</h2>" + grid(
        ["Agent", "Share", "95% interval", "Cases consistent"], rows
    )


def causes_section():
    return (
        "<h2>Why the agents fail: the causes</h2>"
        "<p>The causes of the critical errors are written in docs/results/failures.md "
        "(screen 6 of the site holds them). (a) the engine and the label read a purchase "
        "date in a policy gap differently, or the engine reads a clause without its "
        "condition; (b) an escalation trigger did not fire; (c) a rule the agent did not "
        "apply; (d) the label is wrong by its own criterion; (e) another cause. The system "
        "has 5 cases of cause (a) and 1 of cause (d); the naive and cheap-strong agents "
        "decide every out-of-scope request as a refund instead of escalating, and read "
        "thresholds on the wrong side or from the wrong version. Nothing frozen changes: a "
        "cause found is reported, never fixed into these numbers.</p>"
    )


def delays_section(delays=None):
    """The limitation of the delay reading (T58, ADR-0008), with the sensitivity figures
    when `delays` (eval.delays.analyze's output) is given."""
    return (
        "<h2>Limitation: delays and the passenger who flew</h2>"
        f"<p>{esc(delay_reading.limitation(delays))}</p>"
    )


def render(report, delays=None):
    r = report["run"]
    meta = (
        f"<p>Run date {esc(r['date'])}; tag {esc(r['tag'])} at commit "
        f"{esc(r['tag_commit'])}; test hash {esc(r['test_hash'])}; model "
        f"{esc(r['model'])}; {report['cases']} test cases after exclusions.</p>"
    )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Confirmatory report</title><style>{STYLE}</style></head><body>"
        f"{notices(report)}<h1>Confirmatory report</h1>{meta}"
        + primary_section(report)
        + delays_section(delays)
        + "<h2>Secondary, all test cases</h2>"
        + agent_table(report["secondary"], SECONDARY)
        + "<p>Version errors per 100 runs: registered counts a clause id written in the "
        "rule_version field as a version; corrected counts only version ids "
        "(prereg section 8, computation fault, both values shown).</p>"
        + consistency_section(report)
        + errors_section(report)
        + cost_section(report)
        + by_section("By case type", report["by_type"], report)
        + by_section("By airline", report["by_airline"], report)
        + dot_section(report)
        + exclusions_section(report)
        + models_section(report)
        + grid_section(report)
        + causes_section()
        + "</body></html>\n"
    )


def build(root, runs_dir=None):
    """Write runs/confirm/report.json and report.html; returns the report. Raises
    NotComplete before writing anything when the run is not complete."""
    root = Path(root)
    runs_dir = Path(runs_dir) if runs_dir else root / "runs"
    tests, dot = runner.load_test_cases(root)
    report = analyze(root, runs_dir, tests, dot)
    out = runs_dir / RUN
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (out / "report.html").write_text(
        render(report, delay_reading.analyze(root, runs_dir))
    )
    return report


def exit_code(report):
    """1 when an agent's run is incomplete or invalid, else 0."""
    return 1 if report["incomplete"] or report["invalid"] else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(runner.ROOT))
    ap.add_argument("--runs-dir")
    a = ap.parse_args(argv)
    try:
        report = build(a.root, a.runs_dir)
    except NotComplete as err:
        print(f"report-confirm: {err}", file=sys.stderr)
        raise SystemExit(2) from None
    runs_dir = Path(a.runs_dir) if a.runs_dir else Path(a.root) / "runs"
    print(f"report: {runs_dir / RUN / 'report.html'}")
    for h, p in report["primary"].items():
        print(f"{h}: {p['verdict']}")
    if exit_code(report):
        print("INCOMPLETE OR INVALID RUN: see the top of the report")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
