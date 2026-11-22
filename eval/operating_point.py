"""The operating point of the system's escalation triggers, fixed once on the full
development set (prereg section 6, "Operating point rule").

Re-scores the cached `runs/dev-full-system` with no model call: for each case-run the trace
holds the gathered facts, the rule and policy versions and the engine's result; only
`triggers.check` is re-run per boundary window of the fixed grid. The setting with the fewest
critical errors (wrong decisions + missed escalations) wins, then the fewest unnecessary
escalations, then the smaller window. The amount threshold stays null (no case has an amount).

Entry: `uv run python -m eval.operating_point [--write] [--root DIR] [--run-dir DIR]`.
`--write` puts the chosen window and the grid in the prereg's section 7 and the window in
config/triggers.yaml.
"""

import argparse
import json
import re
from pathlib import Path

import yaml

from agents.system import tools, triggers
from eval.metrics import LABELS, classify, load_cost_total, read_jsonl

ROOT = Path(__file__).resolve().parent.parent
GRID = (0, 5, 10, 15, 20)
RUN = "dev-full-system"
PREREG = "docs/modules/prereg.md"
TRIGGERS = "config/triggers.yaml"
NO_AMOUNT = float("inf")  # amount_threshold null: no amount ever fires
POINT = re.compile(r"^- \*\*Operating point:\*\* window=(\d+) min$", re.MULTILINE)
BLOCK = re.compile(
    r"^- \*\*Operating point:\*\*.*?(?=^- \*\*Registration commit)",
    re.MULTILINE | re.DOTALL,
)


def choose(grid):
    """The row with fewest critical errors, then fewest unnecessary escalations, then the
    smaller window."""
    return min(
        grid,
        key=lambda r: (r["critical_errors"], r["unnecessary_escalations"], r["window"]),
    )


def _objects(line, carrier):
    """The rule and policy objects of a trace line, rebuilt from their ids."""
    rid = line.get("rule_version")
    rules = {r.id: r for r in tools.all_rule_versions()}
    rule = rules[rid] if rid else tools.Exclusion("from trace")
    pols = {p.id: p for p in tools.all_policy_versions(carrier)}
    ids = line.get("policy_versions") or []
    if "purchase_date" not in line["facts"]:
        policy = tuple(pols[i] for i in ids)
    elif ids:
        policy = pols[ids[0]]
    else:
        policy = tools.Exclusion("from trace")
    return rule, policy


def decision_at(line, carrier, window):
    """The system's decision with the trigger window changed, from one trace line."""
    eng = line["engine"]
    if "facts" not in line:  # no flight: the engine's escalate stands, no trigger ran
        return eng["decision"]
    rule, policy = _objects(line, carrier)
    reasons = triggers.check(line["facts"], rule, policy, window, NO_AMOUNT)
    return "escalate" if reasons else eng["decision"]


def rescore(root=ROOT, run_dir=None, grid=GRID):
    """[{window, critical_errors, unnecessary_escalations}] per window, no model call."""
    root = Path(root)
    run_dir = Path(run_dir) if run_dir else root / "runs" / RUN
    cases = {c["case_id"]: c for c in read_jsonl(root / "cases/dev/cases.jsonl")}
    labels = {x["case_id"]: x["decision"] for x in read_jsonl(root / LABELS)}
    lines = []
    for f in sorted((run_dir / "traces").glob("*.json")):
        cid = json.loads((run_dir / "outputs" / f.name).read_text())["case_id"]
        if cid in cases and cid in labels:
            lines.append(
                (cases[cid]["carrier"], labels[cid], json.loads(f.read_text())[0])
            )
    rows = []
    for w in grid:
        kinds = [classify(decision_at(t, c, w), lab) for c, lab, t in lines]
        rows.append(
            {
                "window": w,
                "critical_errors": kinds.count("wrong") + kinds.count("missed"),
                "unnecessary_escalations": kinds.count("unnecessary"),
            }
        )
    return rows


def prereg_block(grid, chosen, runs, dollars):
    table = "\n".join(
        f"| {r['window']} | {r['critical_errors']} | {r['unnecessary_escalations']} |"
        for r in grid
    )
    return (
        f"- **Operating point:** window={chosen['window']} min\n"
        f"- **Operating point grid:** full development set, system agent, {runs} case-runs, "
        f"cost USD {dollars:.4f}; amount threshold null (no case has an amount); rule: fewest "
        f"critical errors, then fewest unnecessary escalations, then the smaller window.\n\n"
        f"| window (min) | critical errors | unnecessary escalations |\n|---|---|---|\n"
        f"{table}\n\n"
    )


def write(root, grid, chosen, runs, dollars):
    root = Path(root)
    path = root / PREREG
    text = path.read_text(encoding="utf-8")
    block = prereg_block(grid, chosen, runs, dollars)
    if BLOCK.search(text):
        text = BLOCK.sub(lambda _: block, text, count=1)
    else:
        text = text.replace(
            "- **Registration commit:**", block + "- **Registration commit:**", 1
        )
    path.write_text(text, encoding="utf-8")
    tpath = root / TRIGGERS
    lines = [
        f"window_minutes: {chosen['window']}" if x.startswith("window_minutes:") else x
        for x in tpath.read_text(encoding="utf-8").splitlines()
    ]
    tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_recorded(root):
    """(window in the prereg, window in triggers.yaml, grid rows of the prereg table)."""
    root = Path(root)
    window, rows = recorded_grid((root / PREREG).read_text(encoding="utf-8"))
    yml = yaml.safe_load((root / TRIGGERS).read_text(encoding="utf-8"))
    return window, yml["window_minutes"], rows


def recorded_grid(text):
    """(the window of the prereg's operating point, the rows of its grid table) from the
    prereg's text."""
    m = POINT.search(text)
    rows = [
        {"window": int(a), "critical_errors": int(b), "unnecessary_escalations": int(c)}
        for a, b, c in re.findall(
            r"^\| (\d+) \| (\d+) \| (\d+) \|$", text, re.MULTILINE
        )
    ]
    return (int(m.group(1)) if m else None), rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--run-dir")
    a = ap.parse_args(argv)
    run_dir = Path(a.run_dir) if a.run_dir else Path(a.root) / "runs" / RUN
    if not (run_dir / "traces").is_dir():
        raise SystemExit(
            f"no run at {run_dir}: run `make dev-full BUDGET= CEILING=` first"
        )
    grid = rescore(a.root, run_dir)
    chosen = choose(grid)
    for r in grid:
        print(
            f"window {r['window']:>2}: {r['critical_errors']} critical, "
            f"{r['unnecessary_escalations']} unnecessary"
        )
    print(f"operating point: window={chosen['window']} min")
    if a.write:
        runs = len(list((run_dir / "traces").glob("*.json")))
        write(a.root, grid, chosen, runs, load_cost_total(run_dir))


if __name__ == "__main__":
    main()
