"""The delay reading of the registered study, as a sensitivity analysis (card T58, ADR-0008).

`python -m eval.delays [--root .] [--runs-dir runs] [--doc docs/results/delays.md]` reads the
frozen confirmatory runs and labels and rereads the delay cases: the saved rule texts owe the
refund for a significantly delayed flight only to a passenger who chooses not to fly it, and
no case says the passenger did not fly. So every included test case whose frozen label is
`refund`, whose facts say `cancelled: false` and carry no `renumbered: true` (the refund then
rests on the delay) is read as `no_refund`, unless its facts say `travelled: false`. Nothing
frozen changes: the labels, the engine, the runs and the prereg stay as registered; this is a
sensitivity analysis decided after the results, and the document says so.

Per agent: wrong decisions, missed escalations and critical errors per 100 runs, registered
and after the flip, and H2's comparison (system minus each other agent) with its 95% interval
from `eval.confirm.analyze` rerun with the overridden labels, the registered seed and
resamples. The tables go between `<!-- generated:NAME -->` markers in the document, as
`eval.failures` writes its own; `--check` writes nothing and exits 1 when a table differs from
a rerun. No model call.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from eval import confirm, failures, metrics
from eval.consistency import RESAMPLES, SEED

AGENTS = failures.AGENTS
DOC = "docs/results/delays.md"
ADR = "docs/decisions/0008-delay-refund-when-the-passenger-did-not-fly.md"
FLIPPED_TO = "no_refund"


def fact(case, name):
    """The value of a case's fact, or None when the case does not carry it."""
    f = (case.get("facts") or {}).get(name)
    return f.get("value") if isinstance(f, dict) else f


def flipped(cases, labels):
    """{case id: FLIPPED_TO} for each case whose `refund` label rests on the delay: the facts
    say `cancelled: false`, not `renumbered: true`, and not `travelled: false` (the fact that
    keeps the label: the passenger did not fly)."""
    out = {}
    for cid, c in sorted(cases.items()):
        label = labels.get(cid)
        if (
            label
            and label["decision"] == "refund"
            and fact(c, "cancelled") is False
            and fact(c, "renumbered") is not True
            and fact(c, "travelled") is not False
        ):
            out[cid] = FLIPPED_TO
    return out


def override_root(root, override, into):
    """A tree under `into` that `confirm.analyze` reads as `root`, its labels.jsonl with the
    decision of each case in `override` replaced; the other files are links to `root`'s."""
    root, into = Path(root), Path(into)
    labels = into / metrics.LABELS
    labels.parent.mkdir(parents=True)
    rows = metrics.read_jsonl(root / metrics.LABELS)
    labels.write_text(
        "".join(
            json.dumps({**r, "decision": override.get(r["case_id"], r["decision"])})
            + "\n"
            for r in rows
        )
    )
    for rel in ("data/labels/dot", "rules", "docs/modules/prereg.md"):
        src = root / rel
        if src.exists():
            dst = into / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src.resolve())
    return into


def h2_report(root, runs_dir, override):
    """The H2 block of `confirm.analyze` with `override` applied to the labels."""
    root = Path(root)
    tests = metrics.read_jsonl(root / "cases/test/cases.jsonl")
    dot_path = root / "cases/test/dot/cases.jsonl"
    dot = metrics.read_jsonl(dot_path) if dot_path.exists() else []
    with tempfile.TemporaryDirectory() as tmp:
        tree = override_root(root, override, tmp)
        report = confirm.analyze(
            tree, runs_dir, tests, dot, resamples=RESAMPLES, seed=SEED
        )
    return report["primary"]["H2"]


def analyze(root, runs_dir):
    """Every figure of the document, as one dict."""
    cases, labels, table, ent = failures.load(root, runs_dir)
    over = flipped(cases, labels)
    data = {
        "flipped": over,
        "by_type": {},
        "cases": len(cases),
        "agents": {},
    }
    for cid in over:
        data["by_type"].setdefault(cases[cid]["type"], []).append(cid)
    runs_dir = Path(runs_dir)
    for a in AGENTS:
        d = runs_dir / f"{confirm.RUN}-{a}"
        rs = failures.rows(metrics.load_outputs(d), cases, labels, table, ent)
        data["agents"][a] = {
            "registered": failures.h2(rs),
            "flipped": failures.h2(rs, over),
        }
    data["h2"] = {
        "registered": h2_report(root, runs_dir, {}),
        "flipped": h2_report(root, runs_dir, over),
    }
    return data


# --- rendering ---------------------------------------------------------------


def table_flipped(data):
    lines = [
        (
            f"{len(data['flipped'])} of the {data['cases']} included test cases, read as "
            f"{FLIPPED_TO}:"
        ),
        "",
        "| Case type | Cases | Ids |",
        "|---|---|---|",
    ]
    for t, ids in sorted(data["by_type"].items()):
        lines.append(f"| {t} | {len(ids)} | {', '.join(ids)} |")
    return "\n".join(lines)


def table_figures(data):
    lines = [
        (
            "| Agent | Wrong per 100 (registered) | Wrong per 100 (flipped) | "
            "Missed per 100 (registered) | Missed per 100 (flipped) | "
            "Critical per 100 (registered) | Critical per 100 (flipped) |"
        ),
        "|---|---|---|---|---|---|---|",
    ]
    for a in AGENTS:
        g, s = data["agents"][a]["registered"], data["agents"][a]["flipped"]
        cells = [
            f"{x[k]:.2f} ({x[k[: -len('_per_100')]]})"
            for k in ("wrong_per_100", "missed_per_100", "critical_per_100")
            for x in (g, s)
        ]
        lines.append(f"| {a} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("Counts of case-runs in brackets.")
    return "\n".join(lines)


def table_h2(data):
    lines = [
        (
            "| System minus | Difference (registered) | 95% interval (registered) | "
            "Difference (flipped) | 95% interval (flipped) | Meets the criterion (flipped) |"
        ),
        "|---|---|---|---|---|---|",
    ]
    reg = {c["other"]: c for c in data["h2"]["registered"]["comparisons"]}
    flip = {c["other"]: c for c in data["h2"]["flipped"]["comparisons"]}
    for other in sorted(flip):
        r, f = reg[other], flip[other]
        lines.append(
            f"| {other} | {r['difference']:.2f} | [{r['low']:.2f}, {r['high']:.2f}] | "
            f"{f['difference']:.2f} | [{f['low']:.2f}, {f['high']:.2f}] | "
            f"{'yes' if f['meets_criterion'] else 'no'} |"
        )
    lines.append("")
    lines.append(
        f"Intervals: paired cluster bootstrap, seed {SEED}, {RESAMPLES:,} resamples, as "
        "registered. H2 is met when every interval lies entirely below 0. Verdict, registered: "
        f"{data['h2']['registered']['verdict']}; flipped: {data['h2']['flipped']['verdict']}."
    )
    return "\n".join(lines)


def render(data):
    """{marker name: generated markdown}."""
    return {
        "flipped": table_flipped(data),
        "figures": table_figures(data),
        "h2": table_h2(data),
    }


def limitation(data=None):
    """The one plain paragraph of the confirmatory report and the site: the limitation, with
    the sensitivity figures when `data` (the output of `analyze`) is given."""
    text = (
        "Limitation: the study reads a domestic arrival delay of 3 hours or more as a refund "
        "even when the passenger flew the delayed flight. The saved rule texts (49 U.S.C. "
        "42305(a), 14 CFR 260.6) owe that refund only to a passenger who chooses not to fly "
        "it, and no test case says the passenger did not fly. The registered labels and "
        "numbers are unchanged. "
    )
    if data is None:
        return text + f"The reading is in ADR-0008 ({ADR})."
    s, r = data["agents"]["system"]["flipped"], data["agents"]["system"]["registered"]
    comps = ", ".join(
        f"system minus {c['other']} {c['difference']:.2f} "
        f"[{c['low']:.2f}, {c['high']:.2f}]"
        for c in data["h2"]["flipped"]["comparisons"]
    )
    return (
        text
        + f"A sensitivity analysis decided after the results reads the {len(data['flipped'])} "
        f"refund labels that rest on a delay as no_refund (none says the passenger did not "
        f"fly): the system then makes {s['critical_per_100']:.2f} "
        f"critical errors per 100 runs (registered {r['critical_per_100']:.2f}), and "
        f"H2's difference with its 95% interval is {comps} "
        f"(H2 {data['h2']['flipped']['verdict']}). The reading is in ADR-0008 ({ADR})."
    )


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m eval.delays")
    p.add_argument("--root", default=".")
    p.add_argument("--runs-dir", default="runs")
    p.add_argument("--doc", default=DOC)
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    doc = Path(args.root) / args.doc
    sections = render(analyze(args.root, args.runs_dir))
    text = doc.read_text(encoding="utf-8")
    missing = failures.missing_markers(text, sections)
    if missing:
        print(f"{doc}: no markers for {', '.join(missing)}", file=sys.stderr)
        return 1
    new = failures.splice(text, sections)
    if args.check:
        if new != text:
            print(f"{doc}: the generated tables differ from a rerun", file=sys.stderr)
            return 1
        print(f"{doc}: the generated tables match a rerun")
        return 0
    if new != text:
        doc.write_text(new, encoding="utf-8")
    print(f"{doc}: {len(sections)} generated tables written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
