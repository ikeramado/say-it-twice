"""The 130 test cases decided again with the delay rule fixed to the law's words (card T64).

`python -m eval.fixed_rule [--root .] [--runs-dir runs] [--doc docs/results/fixed-rule.md]
[--check]`. ADR-0008: the rule gives the refund for a significant delay only to a passenger
who did not fly it. The corrected reading replaces the registered engine's delay path only
(`agents/` is not touched): a delay of the federal threshold gives a refund only when a fact
says `travelled: false`; an airline's own delay threshold is read as the engine reads it (a
contract may give more than the rule). Candidate weighing, the triggers and every escalation
stay as registered.

Each run of the system is decided again from the facts its trace holds (the delay) and the
case's own facts (`cancelled`, `renumbered`, `travelled`); the rule and the policy are rebuilt
from the trace's ids with the `agents.system.tools` loaders. A run with no facts in its trace
keeps its registered decision (`eval.confirm.mapped`). No model call. The corrected figures
are exploratory: a fix made after seeing the test results, to be checked on new cases (the
monthly prospective set, S6). Nothing registered changes.
"""

import argparse
import contextlib
import json
import sys
from pathlib import Path

from agents.system import engine, tools
from eval import confirm, delays, failures, metrics

DOC = "docs/results/fixed-rule.md"
RUN = f"{confirm.RUN}-{confirm.SYSTEM}"
CASE_FACTS = ("cancelled", "renumbered", "travelled")


def _federal_clause(rule):
    return engine._rule_clause(rule, "delay-definition") or engine._rule_clause(
        rule, "delay"
    )


def fixed_delay_path(f, rule, pol, fallback):
    """The engine's `_delay_path` with the federal delay refunded only when the passenger did
    not fly (`travelled: false`); the airline's own threshold stands as the engine reads it."""
    full = engine._sources(rule, pol)
    if not full:
        return "escalate", fallback or engine._cancel_clause(rule, pol)
    src = []
    if pol is not None:
        t = engine._policy_threshold(pol)
        if t:
            src.append((t[0], t[1], engine._policy_clause(pol)))
    if f.get("travelled") is False:
        fed = engine._federal_threshold(rule)
        if fed:
            src.append((fed[0], fed[1], _federal_clause(rule)))
    src.sort(key=lambda s: s[1])
    if src and f["arrival_delay_min"] >= src[0][1]:
        return "refund", src[0][2]
    return "no_refund", (src or full)[0][2]


@contextlib.contextmanager
def corrected_reading():
    """The engine with the corrected delay path, restored on exit."""
    old = engine._delay_path
    engine._delay_path = fixed_delay_path
    try:
        yield
    finally:
        engine._delay_path = old


def rebuild(case, line):
    """(facts, rule, policy) of a trace line, from its ids and the case's own facts."""
    facts = dict(line["facts"])
    for k in CASE_FACTS:
        v = delays.fact(case, k)
        if v is not None:
            facts[k] = v
    rules = {r.id: r for r in tools.all_rule_versions()}
    rule = rules.get(line["rule_version"]) or tools.Exclusion("no rule")
    by_id = {p.id: p for p in tools.all_policy_versions(case["carrier"])}
    pols = tuple(by_id[i] for i in line["policy_versions"])
    if "purchase_date" in facts:
        policy = (
            pols[0] if len(pols) == 1 else pols or tools.Exclusion("no policy version")
        )
    else:
        policy = pols + (None,)
    return facts, rule, policy


def decide(case, out, line, corrected=True):
    """One run's decision: the engine's (corrected, or as registered) unless a trigger fired;
    a run without facts keeps its registered decision."""
    if not line or not line.get("facts"):
        return confirm.mapped(out)
    if line.get("triggers"):
        return "escalate"
    facts, rule, policy = rebuild(case, line)
    if corrected:
        with corrected_reading():
            return engine.decide(facts, rule, policy)["decision"]
    return engine.decide(facts, rule, policy)["decision"]


def load_trace(run_dir, out):
    path = Path(run_dir) / "traces" / f"{out['case_id']}_{out.get('run', 0)}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return data[0] if data else None


def figures(decisions, labels):
    """Cases with ten identical decisions, and cases whose every decision is the label."""
    return {
        "consistent": sum(1 for d in decisions.values() if len(set(d)) == 1),
        "correct": sum(
            1 for c, d in decisions.items() if all(x == labels[c] for x in d)
        ),
    }


def analyze(root, runs_dir):
    """`consistent` and `correct` (corrected reading, against the labels as ADR-0008 reads
    them), `registered` (the registered decisions, against the frozen and the ADR-0008
    labels) and `cases` (case id to its ten corrected decisions)."""
    cases, labels, _, _ = failures.load(root, runs_dir)
    over = delays.flipped(cases, labels)
    frozen = {c: x["decision"] for c, x in labels.items()}
    adr = {c: over.get(c, d) for c, d in frozen.items()}
    run_dir = Path(runs_dir) / RUN
    outs = {}
    for o in sorted(metrics.load_outputs(run_dir), key=lambda o: o.get("run", 0)):
        if o["case_id"] in cases:
            outs.setdefault(o["case_id"], []).append(o)
    fixed, registered = {}, {}
    for cid, rows in sorted(outs.items()):
        lines = [load_trace(run_dir, o) for o in rows]
        fixed[cid] = [decide(cases[cid], o, ln) for o, ln in zip(rows, lines)]
        registered[cid] = [confirm.mapped(o) for o in rows]
    fig = figures(fixed, adr)
    reg = figures(registered, frozen)
    return {
        **fig,
        "total": len(fixed),
        "registered": {**reg, "correct_adr": figures(registered, adr)["correct"]},
        "cases": fixed,
        "labels": adr,
    }


# --- rendering ---------------------------------------------------------------


def table_figures(data):
    r, n = data["registered"], data["total"]
    return "\n".join(
        [
            "| Reading | Cases with ten identical decisions | Cases correct in all ten runs |",
            "|---|---|---|",
            f"| Registered, frozen labels | {r['consistent']} of {n} | {r['correct']} of {n} |",
            f"| Registered, ADR-0008 labels | {r['consistent']} of {n} | {r['correct_adr']} of {n} |",
            f"| Corrected, ADR-0008 labels | {data['consistent']} of {n} | {data['correct']} of {n} |",
            "",
            "ADR-0008 labels: the frozen labels, each refund that rests on a delay read as no_refund.",
        ]
    )


def table_cases(data):
    lines = ["| Case | ADR-0008 label | Ten corrected decisions |", "|---|---|---|"]
    for cid, ds in data["cases"].items():
        lines.append(f"| {cid} | {data['labels'][cid]} | {' '.join(ds)} |")
    return "\n".join(lines)


def render(data):
    """{marker name: generated markdown}."""
    return {"figures": table_figures(data), "cases": table_cases(data)}


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m eval.fixed_rule")
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
