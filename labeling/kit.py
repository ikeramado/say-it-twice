"""The labeling kit (ADR-0004): labelers `opus`, `sonnet` and `rules`; the human resolves the rest.

Every function takes `root`, the repository root, so tests run on a temporary tree.
Cases are read from cases/dev/cases.jsonl and cases/test/cases.jsonl only, never
cases/test/dot/. This module never imports agents/ or eval/.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

from rules import lookup

ROOT = Path(__file__).resolve().parent.parent
CASE_FILES = ("cases/dev/cases.jsonl", "cases/test/cases.jsonl")
LABELERS = ("opus", "sonnet", "rules")
FIELDS = ("case_id", "decision", "clause", "rule_version", "policy_version")
DECISIONS = ("refund", "no_refund", "escalate")
EXCLUDE = "exclude"
SALT = "say-it-twice-labels"


class LabelingError(Exception):
    pass


def work(root: Path) -> Path:
    return Path(root) / "labeling" / "work"


def load_cases(root: Path) -> list[dict]:
    out = []
    for rel in CASE_FILES:
        path = Path(root) / rel
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


# --- opaque ids -----------------------------------------------------------


def opaque_id(case_id: str) -> str:
    """A stable id that says nothing of the case type: SHA-256 of case id + SALT, 10 hex."""
    return hashlib.sha256((case_id + SALT).encode("utf-8")).hexdigest()[:10]


def write_map(root: Path, cases: list[dict]) -> Path:
    """labeling/work/map.json, opaque id to case id, outside every labeler's folder."""
    path = work(root) / "map.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    mapping = {opaque_id(c["case_id"]): c["case_id"] for c in cases}
    if len(mapping) != len(cases):
        raise LabelingError("two cases share an opaque id")
    path.write_text(json.dumps(mapping, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_map(root: Path) -> dict[str, str]:
    path = work(root) / "map.json"
    if not path.exists():
        return json.loads(write_map(root, load_cases(root)).read_text(encoding="utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


# --- sheets ---------------------------------------------------------------


def _fact_value(case: dict, name: str):
    f = case.get("facts", {}).get(name)
    return None if f is None else f.get("value")


def _clauses_md(clauses) -> list[str]:
    return [f"- `{c.id}` ({c.section}, {c.topic}): {c.text}" for c in clauses]


def sheet_text(case: dict) -> str:
    """The sheet: the case and the texts in force, nothing the labeler must not see."""
    flight_date = date.fromisoformat(case["flight_date"])
    purchase = _fact_value(case, "purchase_date")
    renumbered = bool(_fact_value(case, "renumbered"))
    lines = [
        f"# Case {opaque_id(case['case_id'])}",
        "",
        "## Flight record",
        "",
        f"- Carrier: {case['carrier']}",
        f"- Flight number: {case['flight_number']}",
        f"- Origin: {case['origin']}",
        f"- Flight date: {case['flight_date']}",
        f"- Purchase date: {purchase if purchase else 'not given'}",
        "",
        "## Passenger facts",
        "",
    ]
    for name in sorted(case.get("facts", {})):
        lines.append(f"- {name}: {json.dumps(_fact_value(case, name))}")
    lines += ["", "## Customer message", "", case["message"]["text"], ""]
    lines += ["## Rule version in force on the flight date", ""]
    rule = lookup.rule_for(flight_date, renumbered)
    if isinstance(rule, lookup.Exclusion):
        lines.append(f"None pinned down: {rule.reason}")
    else:
        lines.append(f"Version `{rule.id}`, from {rule.first_day} to {rule.last_day or 'now'}.")
        lines += [""] + _clauses_md(rule.clauses)
        versions = {v.id: v for v in lookup.rule_versions()}
        seen, parent = {rule.id}, rule.follows
        while parent and parent not in seen:
            seen.add(parent)
            base = versions[parent]
            lines += ["", f"### Inherited from version `{base.id}` (`{rule.id}` follows it)", ""]
            lines += _clauses_md(base.clauses)
            parent = base.follows
    lines += ["", f"## Airline policy of {case['carrier']} for the purchase date", ""]
    if purchase:
        pol = lookup.policy_for(case["carrier"], date.fromisoformat(purchase))
        if isinstance(pol, lookup.Exclusion):
            lines.append(f"None pinned down: {pol.reason}")
        else:
            lines.append(f"Version `{pol.id}`.")
            lines += [""] + _clauses_md(pol.clauses)
    else:
        lines.append("The purchase date is not given; every version on file, with its coverage:")
        for pol in lookup.policy_versions(case["carrier"]) or ():
            cov = ", ".join(f"{a} to {b or 'now'}" for a, b in pol.coverage)
            lines += ["", f"### Version `{pol.id}` (purchases {cov})", ""]
            lines += _clauses_md(pol.clauses)
    lines += [
        "",
        "## Your answer",
        "",
        (
            "One row in answers.csv: case_id, decision (refund, no_refund or escalate), "
            "clause (the clause id that justifies it), rule_version, policy_version."
        ),
        "",
    ]
    return "\n".join(lines)


def _write_template(path: Path, case_ids) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        for cid in case_ids:
            w.writerow([cid, "", "", "", ""])


def write_sheets(root: Path, who: str, cases: list[dict]) -> Path:
    write_map(root, load_cases(root))
    cases = sorted(cases, key=lambda c: opaque_id(c["case_id"]))
    out = work(root) / who
    sheets = out / "sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    for c in cases:
        (sheets / f"{opaque_id(c['case_id'])}.md").write_text(sheet_text(c), encoding="utf-8")
    _write_template(out / "answers.csv", [opaque_id(c["case_id"]) for c in cases])
    return sheets


def label_sheets(root: Path, labeler: str) -> Path:
    if labeler not in LABELERS:
        raise LabelingError(f"unknown labeler {labeler!r}; the labelers are {LABELERS}")
    return write_sheets(root, labeler, load_cases(root))


# --- answers --------------------------------------------------------------


def read_answers(path: Path, root: Path | None = None) -> dict[str, dict]:
    """Answers by case id; with root, the opaque ids are translated back through map.json."""
    if not path.exists():
        raise LabelingError(f"no answers at {path}")
    mapping = read_map(root) if root is not None else {}
    out = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            if row.get("case_id"):
                cid = mapping.get(row["case_id"], row["case_id"])
                out[cid] = {f: row.get(f, "") for f in FIELDS} | {"case_id": cid}
    return out


def import_answers(root: Path, labeler: str, case_ids=None) -> dict:
    """Validate a labeler's answers; report missing cases and bad decisions."""
    if case_ids is None:
        case_ids = [c["case_id"] for c in load_cases(root)]
    answers = read_answers(work(root) / labeler / "answers.csv", root)
    missing = [c for c in case_ids if not answers.get(c, {}).get("decision")]
    invalid = [
        c for c, a in answers.items() if a["decision"] and a["decision"] not in DECISIONS
    ]
    unknown = sorted(set(answers) - set(case_ids))
    return {"answered": len(answers) - len(missing), "missing": missing,
            "invalid": invalid, "unknown": unknown}


# --- kappa ----------------------------------------------------------------


def cohen_kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    if n == 0 or n != len(b):
        raise LabelingError("kappa needs two equal, non-empty lists")
    po = sum(x == y for x, y in zip(a, b)) / n
    cats = set(a) | set(b)
    pe = sum((a.count(k) / n) * (b.count(k) / n) for k in cats)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def _resolutions(root: Path) -> dict[str, dict]:
    path = work(root) / "resolutions.csv"
    out = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                if row.get("case_id") and row.get("decision"):
                    out[row["case_id"]] = row
    return out


def _pairs():
    return [(a, b) for i, a in enumerate(LABELERS) for b in LABELERS[i + 1:]]


def compare(root: Path) -> dict:
    """Three-way comparison on `decision` over the cases all labelers answered.

    `agreed`: the three give the same decision; the row is the rules labeler's (clause and
    version fields). `carried`: an earlier resolution whose decision equals the rules
    labeler's, never an `exclude`. `disagreements`: the cases where the three do not all
    agree and no resolution is carried, listed in disagreements.csv with each labeler's
    answer and the earlier resolution, if any. A resolution with a non-empty `reviewed`
    column is the human's decision under ADR-0004 and settles the case.
    """
    ans = {lab: read_answers(work(root) / lab / "answers.csv", root) for lab in LABELERS}
    both = sorted(c for c in ans[LABELERS[0]]
                  if all(ans[lab].get(c, {}).get("decision") for lab in LABELERS))
    kappas = {f"{a}-{b}": cohen_kappa([ans[a][c]["decision"] for c in both],
                                      [ans[b][c]["decision"] for c in both])
              for a, b in _pairs()} if both else {}
    unanimous = [c for c in both if len({ans[lab][c]["decision"] for lab in LABELERS}) == 1]
    res = _resolutions(root)
    rules = ans["rules"]
    carried = {c: res[c] for c in both if c not in unanimous and c in res
               and res[c]["decision"] in DECISIONS
               and res[c]["decision"] == rules[c]["decision"]}
    reviewed = {c: res[c] for c in both if c not in unanimous and c not in carried
                and c in res and res[c].get("reviewed")}
    dis = [c for c in both if c not in unanimous and c not in carried and c not in reviewed]
    path = work(root) / "disagreements.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id"] + [f"{lab}_{f}" for lab in LABELERS for f in FIELDS[1:]]
                   + ["resolution_decision", "resolution_clause", "resolution_reason"])
        for c in dis:
            r = res.get(c, {})
            w.writerow([c] + [ans[lab][c][f] for lab in LABELERS for f in FIELDS[1:]]
                       + [r.get("decision", ""), r.get("clause", ""), r.get("reason", "")])
    return {"n": len(both), "kappas": kappas,
            "three_way": len(unanimous) / len(both) if both else 0.0,
            "disagreements": dis, "carried": carried, "reviewed": reviewed,
            "agreed": {c: ans["rules"][c] for c in unanimous}, "path": path}


# --- freeze ---------------------------------------------------------------


def label_freeze(root: Path) -> dict:
    """Write data/labels/labels.jsonl from agreed, carried and resolved cases.

    Excluded cases go to excluded.md. Refuses while any disagreement is unresolved. A
    resolution row whose decision is `exclude` and that the human reviewed excludes the case,
    with its `reason` column.
    """
    case_ids = [c["case_id"] for c in load_cases(root)]
    cmp = compare(root)
    if cmp["disagreements"]:
        raise LabelingError(f"{len(cmp['disagreements'])} disagreements unresolved: "
                            f"{cmp['disagreements']}")
    settled = {**cmp["carried"], **cmp["reviewed"]}
    unlabeled = [c for c in case_ids if c not in cmp["agreed"] and c not in settled]
    if unlabeled:
        raise LabelingError(f"{len(unlabeled)} cases lack an answer from the three labelers: "
                            f"{unlabeled}")
    labels, excluded = [], []
    for c in case_ids:
        if c in settled:
            r = settled[c]
            if r["decision"] == EXCLUDE:
                excluded.append((c, r.get("reason") or "no reason given"))
                continue
            if r["decision"] not in DECISIONS:
                raise LabelingError(f"resolution for {c} has decision {r['decision']!r}")
            labels.append({f: r.get(f, "") for f in FIELDS})
        else:
            labels.append(dict(cmp["agreed"][c]))
    out = Path(root) / "data" / "labels" / "labels.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in labels),
                   encoding="utf-8")
    lines = ["# Excluded cases", "",
             "Cases still unresolved after the human read the rule text (ADR-0004).", ""]
    lines += [f"- `{c}`: {why}" for c, why in excluded] or ["None."]
    (Path(root) / "labeling" / "excluded.md").write_text("\n".join(lines) + "\n",
                                                         encoding="utf-8")
    return {"labels": len(labels), "excluded": excluded, "path": out}
