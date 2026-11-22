"""The development metrics of the prereg's sections 5 and 6, per agent and per case type.

Reads runs/<protocol>-<agent>/outputs and costs.jsonl, cases/dev/cases.jsonl, the frozen
labels and rules/versions.yaml; `eval/` is the only package that reads the labels.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from eval.consistency import case_consistent, consistency_share

DECISIONS = ("refund", "no_refund", "escalate")
ENTITLEMENTS = Path(__file__).resolve().parent / "entitlements.yaml"
LABELS = "data/labels/labels.jsonl"
VERSION_ID = re.compile(r"\bv\d+\b")
POLICY_ID = re.compile(r"\b([A-Z]{2})-\d{4}-\d{2}-\d{2}")

COUNTS = (
    "correct",
    "wrong_decisions",
    "missed_escalations",
    "needed_escalations",
    "unnecessary_escalations",
    "version_errors",
    "invented_entitlements",
    "policy_leaks",
    "parse_errors",
)


KIND_COUNT = {
    "correct": "correct",
    "needed": "needed_escalations",
    "wrong": "wrong_decisions",
    "missed": "missed_escalations",
    "unnecessary": "unnecessary_escalations",
}


def read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def load_outputs(run_dir):
    return [
        json.loads(f.read_text())
        for f in sorted((Path(run_dir) / "outputs").glob("*.json"))
    ]


def load_cost_total(run_dir):
    path = Path(run_dir) / "costs.jsonl"
    if not path.exists():
        return 0.0
    return sum(json.loads(x)["dollars"] for x in path.read_text().splitlines() if x)


def classify(decision, label):
    """correct | wrong | missed | unnecessary | needed (a needed escalation is correct too)."""
    if decision == label:
        return "needed" if label == "escalate" else "correct"
    if label == "escalate":
        return "missed"
    if decision == "escalate":
        return "unnecessary"
    return "wrong"


def in_force(table, date):
    """Rule version ids whose first and last day cover the flight date."""
    return {
        v["id"]
        for v in table["versions"]
        if v["first_day"] <= date and (v["last_day"] is None or date <= v["last_day"])
    }


def _not_in_force(cited, case, table):
    ok = in_force(table, case["flight_date"])
    ok |= {
        v["follows"] for v in table["versions"] if v["id"] in ok and v.get("follows")
    }
    return bool(cited - ok)


def version_error(out, case, table):
    """The explanation or the rule_version field cites a version id not in force on the
    flight date. Only version ids (VERSION_ID) count in both: a clause id written in the
    rule_version field is not a version. A version that a version in force names in
    `follows` (one hop) counts as in force: v3 and v4 inherit v2's clauses."""
    cited = set(VERSION_ID.findall(out.get("explanation") or ""))
    cited |= set(VERSION_ID.findall(str(out.get("rule_version") or "")))
    return _not_in_force(cited, case, table)


def version_error_registered(out, case, table):
    """The computation registered before T43: the whole rule_version string counts as a
    cited version (a clause id there is flagged). Shown beside the corrected value."""
    cited = set(VERSION_ID.findall(out.get("explanation") or ""))
    if out.get("rule_version"):
        cited.add(out["rule_version"])
    return _not_in_force(cited, case, table)


def policy_leak(out, case):
    """The clause, the policy version or the explanation names a clause id or policy version
    of the other airline (by its id prefix)."""
    text = " ".join(
        str(out.get(k) or "") for k in ("clause", "policy_version", "explanation")
    )
    return any(p != case["carrier"] for p in POLICY_ID.findall(text))


def label_versions(value):
    return [] if value in (None, "none") else str(value).split(";")


def invented_entitlement(out, label, ent):
    """A vocabulary phrase in the explanation that no version of the case lists."""
    allowed = set()
    for v in label_versions(label.get("rule_version")):
        allowed |= set(ent["rule_versions"].get(v, []))
    for v in label_versions(label.get("policy_version")):
        allowed |= set(ent["policy_versions"].get(v, []))
    text = (out.get("explanation") or "").lower()
    return any(p.lower() in text and p not in allowed for p in ent["vocabulary"])


def modal(decisions):
    counts = Counter(decisions)
    top = max(counts.values())
    return next(d for d in DECISIONS if counts.get(d) == top)


def modal_or_escalate(decisions):
    """The modal decision, or `escalate` when two or more decisions tie for the mode (prereg
    section 5: a tied clean mode counts as escalate, the cheap-strong tie rule)."""
    counts = Counter(decisions)
    top = max(counts.values())
    tied = [d for d in DECISIONS if counts.get(d) == top]
    return tied[0] if len(tied) == 1 else "escalate"


def load_latency_total(run_dir):
    """Seconds over every cost line of a run, cache hits included."""
    path = Path(run_dir) / "costs.jsonl"
    if not path.exists():
        return 0.0
    return sum(
        json.loads(x).get("latency", 0.0)
        for x in path.read_text().splitlines()
        if x.strip()
    )


def latency_per_answer(run_dir):
    """The run's latency (every cost line) over its case-runs (its outputs); cost lines carry
    no case id, so cheap-strong's five samples of a run fall in that run's share. None with
    no output."""
    runs = len(list((Path(run_dir) / "outputs").glob("*.json")))
    return load_latency_total(run_dir) / runs if runs else None


def per100(n, runs):
    return 100 * n / runs if runs else None


def block(
    rows, cases, adversarial, dollars=None, bootstrap=False, mode=modal, latency=None
):
    """Metrics of a list of rows {case, label, out, kind, flags}. mode: the clean case's
    decision an adversarial run is compared with (`modal`, or `modal_or_escalate` for the
    confirmatory H3). latency: the latency per answer, read from the cost lines by the
    caller (outputs carry none that counts every call)."""
    runs = len(rows)
    n = {k: 0 for k in COUNTS}
    registered = 0
    for r in rows:
        n[KIND_COUNT[r["kind"]]] += 1
        if r["kind"] == "needed":
            n["correct"] += 1
        n["version_errors"] += r["version_error"]
        registered += r["version_error_registered"]
        n["invented_entitlements"] += r["invented"]
        n["policy_leaks"] += r["leak"]
        n["parse_errors"] += bool(r["out"].get("parse_error"))
    out = {"runs": runs}
    for k in COUNTS:
        out[k] = n[k]
        out[k + "_per_100"] = per100(n[k], runs)
    out["version_errors_registered_per_100"] = per100(registered, runs)
    out["critical_errors"] = n["wrong_decisions"] + n["missed_escalations"]
    out["critical_errors_per_100"] = per100(out["critical_errors"], runs)
    out["correct_share"] = n["correct"] / runs if runs else None
    by_case = defaultdict(list)
    for r in rows:
        by_case[r["case"]["case_id"]].append(r["out"]["decision"])
    out["cases"] = len(by_case)
    out["consistency_share"] = (
        sum(case_consistent(d) for d in by_case.values()) / len(by_case)
        if by_case
        else None
    )
    if bootstrap and by_case:
        out["consistency"] = consistency_share(
            [cases[c] for c in sorted(by_case)], by_case
        )
    adv = [r for r in rows if r["case"].get("clean_case_id") in adversarial]
    changed = sum(
        r["out"]["decision"] != mode(adversarial[r["case"]["clean_case_id"]])
        for r in adv
    )
    out["adversarial_runs"] = len(adv)
    out["adversarial_changes"] = changed
    out["adversarial_change_share"] = changed / len(adv) if adv else None
    out["dollars"] = (
        dollars
        if dollars is not None
        else sum(r["out"].get("dollars", 0.0) for r in rows)
    )
    out["cost_per_correct_decision"] = (
        out["dollars"] / n["correct"] if n["correct"] else None
    )
    out["latency_per_answer"] = latency
    out["cache_hits"] = sum(r["out"].get("cache_hits", 0) for r in rows)
    return out


def agent_metrics(
    cases, labels, outputs, table, ent, dollars=None, mode=modal, latency=None
):
    """{"overall": block, "by_type": {type: block}, "unlabeled_runs": n}. latency: the
    latency per answer of the whole run, in the overall block only (cost lines carry no case
    id, so no case type has its own)."""
    by_id = {c["case_id"]: c for c in cases}
    rows, unlabeled = [], 0
    for o in outputs:
        case, label = by_id.get(o["case_id"]), labels.get(o["case_id"])
        if case is None or label is None:
            unlabeled += 1
            continue
        rows.append(
            {
                "case": case,
                "label": label,
                "out": o,
                "kind": classify(o["decision"], label["decision"]),
                "version_error": version_error(o, case, table),
                "version_error_registered": version_error_registered(o, case, table),
                "invented": invented_entitlement(o, label, ent),
                "leak": policy_leak(o, case),
            }
        )
    clean = defaultdict(list)
    for o in outputs:
        clean[o["case_id"]].append(o["decision"])
    twins = {
        r["case"]["clean_case_id"]: clean[r["case"]["clean_case_id"]]
        for r in rows
        if r["case"].get("clean_case_id") in clean
    }
    types = defaultdict(list)
    for r in rows:
        types[r["case"]["type"]].append(r)
    return {
        "overall": block(
            rows, by_id, twins, dollars, bootstrap=True, mode=mode, latency=latency
        ),
        "by_type": {t: block(types[t], by_id, twins, mode=mode) for t in sorted(types)},
        "unlabeled_runs": unlabeled,
    }


INVALID_SHARE = 0.5


def network_failures(outputs):
    """Outputs the runner recorded as failed on a network error (no answer was read)."""
    return sum(1 for o in outputs if o.get("network_error") is True)


def parse_error_share(outputs):
    """Outputs with parse_error true over outputs, from each output's own field; None
    when there is no output. Network failures are left out: they were never answers."""
    outputs = [o for o in outputs if o.get("network_error") is not True]
    if not outputs:
        return None
    return sum(1 for o in outputs if o.get("parse_error") is True) / len(outputs)


def invalid(outputs):
    """A run is invalid for an agent when strictly more than half its outputs are
    parse errors: its metrics would measure unreadable answers, not decisions."""
    share = parse_error_share(outputs)
    return share is not None and share > INVALID_SHARE


def evaluate(root, protocol, agents, runs_dir=None):
    """The report of a protocol: metrics per agent, read from runs/<protocol>-<agent>.
    An invalid agent gets no metric block: it is listed in `invalid`, its dollars in
    `invalid_dollars`, and `total_dollars` still counts them. An agent with any network
    failure is incomplete: `incomplete` maps it to that count, it gets no metric block
    either (a rerun completes it from the cache), and its dollars stay in the total."""
    root = Path(root)
    runs_dir = Path(runs_dir) if runs_dir else root / "runs"
    cases = read_jsonl(root / "cases/dev/cases.jsonl")
    labels = {x["case_id"]: x for x in read_jsonl(root / LABELS)}
    table = yaml.safe_load((root / "rules/versions.yaml").read_text())
    ent = yaml.safe_load(ENTITLEMENTS.read_text())
    report = {
        "protocol": protocol,
        "agents": {},
        "invalid": [],
        "invalid_dollars": {},
        "incomplete": {},
    }
    left_out = 0.0
    for a in agents:
        d = runs_dir / f"{protocol}-{a}"
        outputs = load_outputs(d)
        failed = network_failures(outputs)
        if failed:
            report["incomplete"][a] = failed
        if invalid(outputs):
            report["invalid"].append(a)
            report["invalid_dollars"][a] = load_cost_total(d)
        if failed or a in report["invalid"]:
            left_out += load_cost_total(d)
            continue
        report["agents"][a] = agent_metrics(
            cases,
            labels,
            outputs,
            table,
            ent,
            load_cost_total(d),
            latency=latency_per_answer(d),
        )
    report["total_dollars"] = (
        sum(v["overall"]["dollars"] for v in report["agents"].values()) + left_out
    )
    return report
