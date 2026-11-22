"""The confirmatory run's critical errors, classified (tasks.md T5.3, card T42).

`python -m eval.failures [--root .] [--runs-dir runs] [--doc docs/results/failures.md]`
reads runs/confirm-<agent>/outputs (and the system's traces), the test cases and the frozen
labels, and writes the generated tables of the document between its markers
`<!-- generated:NAME -->` and `<!-- /generated:NAME -->`; `--check` writes nothing and exits 1
when a table in the document differs from a rerun. No model call; nothing frozen changes.

Decisions are mapped as the confirmatory analysis maps them (`confirm.mapped`), the cases are
the included test cases (`confirm.exclusions`), and a version error or an invented entitlement
is the one of `eval.metrics`.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from eval import confirm, metrics

AGENTS = ("naive", "cheap_strong", "system")
OTHERS = ("naive", "cheap_strong")
DOC = "docs/results/failures.md"
EXAMPLES = 3
SYSTEM_EXAMPLES = 2
QUOTE_CHARS = 600
# Sensitivity, decided after the results (2026-11-20, the human): test-ren-008's label read as
# cause (d); the frozen label stays escalate, this only recomputes H2 as if it were no_refund.
SENSITIVITY = {"test-ren-008": "no_refund"}
MARK = re.compile(
    r"(<!-- generated:(?P<name>[a-z0-9_]+) -->\n)(?P<body>.*?)(<!-- /generated:(?P=name) -->)",
    re.DOTALL,
)


def load(root, runs_dir):
    """(included test cases by id, their labels, the rule table, the entitlements)."""
    root = Path(root)
    tests = metrics.read_jsonl(root / "cases/test/cases.jsonl")
    labels = {x["case_id"]: x for x in metrics.read_jsonl(root / metrics.LABELS)}
    labels = {k: v for k, v in labels.items() if k in {c["case_id"] for c in tests}}
    _, gone, _ = confirm.exclusions(tests, labels)
    cases = {c["case_id"]: c for c in tests if c["case_id"] not in gone}
    table = yaml.safe_load((root / "rules/versions.yaml").read_text())
    ent = yaml.safe_load(metrics.ENTITLEMENTS.read_text())
    return cases, labels, table, ent


def invented_phrases(out, label, ent):
    """The vocabulary phrases in the explanation that no version of the case lists, in the
    vocabulary's order (the phrases behind `metrics.invented_entitlement`)."""
    allowed = set()
    for v in metrics.label_versions(label.get("rule_version")):
        allowed |= set(ent["rule_versions"].get(v, []))
    for v in metrics.label_versions(label.get("policy_version")):
        allowed |= set(ent["policy_versions"].get(v, []))
    text = (out.get("explanation") or "").lower()
    return [p for p in ent["vocabulary"] if p.lower() in text and p not in allowed]


def rows(outputs, cases, labels, table, ent):
    """One row per included, labeled case-run, sorted by (case id, run)."""
    out = []
    for raw in sorted(outputs, key=lambda o: (o["case_id"], o.get("run", 0))):
        case, label = cases.get(raw["case_id"]), labels.get(raw["case_id"])
        if case is None or label is None:
            continue
        o = {**raw, "decision": confirm.mapped(raw)}
        out.append(
            {
                "case": case,
                "label": label,
                "out": o,
                "kind": metrics.classify(o["decision"], label["decision"]),
                "version_error": metrics.version_error_registered(o, case, table),
                "clause_id_only": clause_id_only(o, case, table),
                "invented": metrics.invented_entitlement(o, label, ent),
                "phrases": invented_phrases(o, label, ent),
            }
        )
    return out


def clause_id_only(out, case, table):
    """A version error only because the recorded rule_version is a clause id ("v2-260.2-delay")
    rather than a version id: without that field the explanation cites no version out of force."""
    rv = out.get("rule_version")
    ids = {v["id"] for v in table["versions"]}
    return (
        bool(rv)
        and rv not in ids
        and metrics.version_error_registered(out, case, table)
        and not metrics.version_error_registered({**out, "rule_version": None}, case, table)
    )


def critical(r):
    return r["kind"] in ("wrong", "missed")


def by_key(rs, key):
    """{key value: {"runs", "wrong", "missed", "critical"}} in key order."""
    out = defaultdict(lambda: {"runs": 0, "wrong": 0, "missed": 0, "critical": 0})
    for r in rs:
        k = key(r)
        out[k]["runs"] += 1
        out[k]["wrong"] += r["kind"] == "wrong"
        out[k]["missed"] += r["kind"] == "missed"
        out[k]["critical"] += critical(r)
    return dict(sorted(out.items()))


def explanation_flags(rs):
    """Among the critical-error runs: how many explanations also carry a version error, an
    invented entitlement, either of them."""
    crit = [r for r in rs if critical(r)]
    return {
        "critical": len(crit),
        "version_error": sum(r["version_error"] for r in crit),
        "clause_id_only": sum(r["clause_id_only"] for r in crit),
        "invented": sum(r["invented"] for r in crit),
        "either": sum(r["version_error"] or r["invented"] for r in crit),
    }


def examples(rs, k=EXAMPLES):
    """Run 0 of the first k case ids, in sorted order, whose run 0 is a critical error."""
    return [r for r in rs if r["out"].get("run", 0) == 0 and critical(r)][:k]


def phrase_counts(rs):
    """{phrase: runs whose explanation states it as an invented entitlement}, by count."""
    c = Counter(p for r in rs for p in r["phrases"])
    return dict(sorted(c.items(), key=lambda x: (-x[1], x[0])))


def first_trace(traces_dir, case_id, run):
    path = Path(traces_dir) / f"{case_id}_{run}.json"
    if not path.exists():
        return {}
    got = json.loads(path.read_text())
    return got[0] if isinstance(got, list) and got else got


def system_cases(rs, traces_dir):
    """Per case with a critical error: runs, critical runs, the engine's decision and clause
    and the policy versions it weighed (run 0's trace), the label's decision and clause."""
    per = defaultdict(list)
    for r in rs:
        per[r["case"]["case_id"]].append(r)
    out = []
    for cid, group in sorted(per.items()):
        n = sum(critical(r) for r in group)
        if not n:
            continue
        t = first_trace(traces_dir, cid, group[0]["out"].get("run", 0))
        eng = t.get("engine") or {}
        out.append(
            {
                "case_id": cid,
                "type": group[0]["case"]["type"],
                "runs": len(group),
                "critical": n,
                "decisions": dict(
                    sorted(Counter(r["out"]["decision"] for r in group).items())
                ),
                "engine_decision": eng.get("decision"),
                "engine_clause": eng.get("clause"),
                "policy_versions": t.get("policy_versions") or [],
                "rule_version": t.get("rule_version"),
                "label_decision": group[0]["label"]["decision"],
                "label_clause": group[0]["label"].get("clause"),
            }
        )
    return out


def h2(rs, override=None):
    """Critical errors, wrong decisions and missed escalations per 100 case-runs (the H2 point
    values, pooled over the included case-runs), each run reclassified against its label's
    decision, or against `override[case_id]` when the case is there."""
    override = override or {}
    n = {"runs": len(rs), "critical": 0, "wrong": 0, "missed": 0}
    for r in rs:
        label = override.get(r["case"]["case_id"], r["label"]["decision"])
        kind = metrics.classify(r["out"]["decision"], label)
        n["wrong"] += kind == "wrong"
        n["missed"] += kind == "missed"
        n["critical"] += kind in ("wrong", "missed")
    for k in ("critical", "wrong", "missed"):
        n[k + "_per_100"] = metrics.per100(n[k], len(rs))
    return n


def analyze(root, runs_dir):
    """Every figure of the document, as one dict."""
    cases, labels, table, ent = load(root, runs_dir)
    runs_dir = Path(runs_dir)
    data = {}
    for a in AGENTS:
        d = runs_dir / f"{confirm.RUN}-{a}"
        rs = rows(metrics.load_outputs(d), cases, labels, table, ent)
        data[a] = {
            "runs": len(rs),
            "critical": sum(critical(r) for r in rs),
            "wrong": sum(r["kind"] == "wrong" for r in rs),
            "missed": sum(r["kind"] == "missed" for r in rs),
            "invented_runs": sum(r["invented"] for r in rs),
            "by_type": by_key(rs, lambda r: r["case"]["type"]),
            "by_airline": by_key(rs, lambda r: r["case"]["carrier"]),
            "flags": explanation_flags(rs),
            "examples": examples(rs),
            "phrases": phrase_counts(rs),
            "invented_examples": [r for r in rs if r["invented"]][:SYSTEM_EXAMPLES],
            "h2": h2(rs),
            "h2_sensitivity": h2(rs, SENSITIVITY),
            "invented_by_type": dict(
                sorted(Counter(r["case"]["type"] for r in rs if r["invented"]).items())
            ),
            "invented_by_decision": dict(
                sorted(
                    Counter(r["out"]["decision"] for r in rs if r["invented"]).items()
                )
            ),
        }
        if a == confirm.SYSTEM:
            data[a]["cases"] = system_cases(rs, d / "traces")
    return data


# --- rendering ---------------------------------------------------------------


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "n/a"


def quote(text, limit=QUOTE_CHARS):
    t = " ".join((text or "").split())
    if len(t) > limit:
        t = t[:limit].rstrip() + " [...]"
    return "> " + t.replace("|", "\\|")


def table_totals(data):
    lines = [
        "| Agent | Case-runs | Wrong decisions | Missed escalations | Critical errors | Runs with an invented entitlement |",
        "|---|---|---|---|---|---|",
    ]
    for a in AGENTS:
        x = data[a]
        lines.append(
            f"| {a} | {x['runs']} | {x['wrong']} | {x['missed']} | {x['critical']} | {x['invented_runs']} |"
        )
    return "\n".join(lines)


def table_system_cases(data):
    lines = [
        "| Case | Type | Critical runs | Decisions | Engine (run 0) | Policy versions weighed | Label |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in data[confirm.SYSTEM]["cases"]:
        ds = ", ".join(f"{k} {v}" for k, v in c["decisions"].items())
        lines.append(
            f"| {c['case_id']} | {c['type']} | {c['critical']} of {c['runs']} | {ds} | "
            f"{c['engine_decision']} by `{c['engine_clause']}` ({c['rule_version']}) | "
            f"{', '.join(c['policy_versions']) or 'none'} | "
            f"{c['label_decision']} by `{c['label_clause']}` |"
        )
    return "\n".join(lines)


def table_by(data, field, title):
    keys = sorted({k for a in OTHERS for k in data[a][field]})
    head = (
        f"| {title} | "
        + " | ".join(f"{a} wrong | {a} missed" for a in OTHERS)
        + " | Case-runs |"
    )
    lines = [head, "|---|" + "---|" * (2 * len(OTHERS) + 1)]
    for k in keys:
        cells = []
        for a in OTHERS:
            v = data[a][field].get(k, {"wrong": 0, "missed": 0})
            cells += [str(v["wrong"]), str(v["missed"])]
        runs = data[OTHERS[0]][field].get(k, {}).get("runs", 0)
        lines.append(f"| {k} | " + " | ".join(cells) + f" | {runs} |")
    return "\n".join(lines)


def table_flags(data):
    lines = [
        "| Agent | Critical-error runs | With a version error | of which only a clause id in rule_version | With an invented entitlement | With either |",
        "|---|---|---|---|---|---|",
    ]
    for a in OTHERS:
        f = data[a]["flags"]
        n = f["critical"]
        lines.append(
            f"| {a} | {n} | {f['version_error']} ({pct(f['version_error'], n)}) | "
            f"{f['clause_id_only']} ({pct(f['clause_id_only'], n)}) | "
            f"{f['invented']} ({pct(f['invented'], n)}) | {f['either']} ({pct(f['either'], n)}) |"
        )
    return "\n".join(lines)


def render_examples(data):
    out = []
    for a in OTHERS:
        out.append(f"**{a}**")
        out.append("")
        for r in data[a]["examples"]:
            o = r["out"]
            flags = [
                n
                for n, on in (
                    ("version error", r["version_error"]),
                    ("invented entitlement", r["invented"]),
                )
                if on
            ]
            out.append(
                f"- {r['case']['case_id']}, run 0: decided {o['decision']} by "
                f"`{o.get('clause')}`, label {r['label']['decision']} ({r['kind']}); "
                f"also: {', '.join(flags) or 'neither'}."
            )
            out.append("")
            out.append("  " + quote(o.get("explanation")))
            out.append("")
    return "\n".join(out).rstrip()


def render_phrases(data):
    s = data[confirm.SYSTEM]
    lines = ["| Phrase | Runs |", "|---|---|"]
    lines += [f"| {p} | {n} |" for p, n in s["phrases"].items()]
    lines.append("")
    lines.append(
        f"{s['invented_runs']} system runs state at least one phrase; a run may state more than one."
        " By case type: "
        + ", ".join(f"{k} {v}" for k, v in s["invented_by_type"].items())
        + ". By the engine's decision: "
        + ", ".join(f"{k} {v}" for k, v in s["invented_by_decision"].items())
        + "."
    )
    lines.append("")
    for r in s["invented_examples"]:
        o = r["out"]
        lines.append(
            f"- {r['case']['case_id']}, run {o.get('run', 0)}: the engine decided {o['decision']} by "
            f"`{o.get('clause')}` (policy {o.get('policy_version')}); the explanation added: "
            f"{', '.join(r['phrases'])}."
        )
        lines.append("")
        lines.append("  " + quote(o.get("explanation")))
        lines.append("")
    return "\n".join(lines).rstrip()


def table_sensitivity(data):
    over = ", ".join(f"{k} as {v}" for k, v in SENSITIVITY.items())
    lines = [
        (
            "| Agent | Critical errors per 100 (registered) | Wrong per 100 (registered) | "
            "Missed per 100 (registered) | Critical errors per 100 (sensitivity) | "
            "Wrong per 100 (sensitivity) | Missed per 100 (sensitivity) |"
        ),
        "|---|---|---|---|---|---|---|",
    ]
    for a in AGENTS:
        g, s = data[a]["h2"], data[a]["h2_sensitivity"]
        cells = [
            f"{x[k]:.2f} ({x[k[: -len('_per_100')]]})"
            for x in (g, s)
            for k in ("critical_per_100", "wrong_per_100", "missed_per_100")
        ]
        lines.append(f"| {a} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(f"Sensitivity label: {over}. Counts of case-runs in brackets.")
    return "\n".join(lines)


def render(data):
    """{marker name: generated markdown}."""
    return {
        "totals": table_totals(data),
        "system_cases": table_system_cases(data),
        "by_type": table_by(data, "by_type", "Case type"),
        "by_airline": table_by(data, "by_airline", "Airline"),
        "flags": table_flags(data),
        "examples": render_examples(data),
        "system_invented": render_phrases(data),
        "sensitivity": table_sensitivity(data),
    }


def splice(text, sections):
    """The document with each marker's body replaced; a marker the sections lack stays."""

    def repl(m):
        name = m.group("name")
        if name not in sections:
            return m.group(0)
        return m.group(1) + sections[name].rstrip() + "\n" + m.group(4)

    return MARK.sub(repl, text)


def missing_markers(text, sections):
    found = {m.group("name") for m in MARK.finditer(text)}
    return sorted(set(sections) - found)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m eval.failures")
    p.add_argument("--root", default=".")
    p.add_argument("--runs-dir", default="runs")
    p.add_argument("--doc", default=DOC)
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    doc = Path(args.root) / args.doc
    sections = render(analyze(args.root, args.runs_dir))
    text = doc.read_text(encoding="utf-8")
    missing = missing_markers(text, sections)
    if missing:
        print(f"{doc}: no markers for {', '.join(missing)}", file=sys.stderr)
        return 1
    new = splice(text, sections)
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
