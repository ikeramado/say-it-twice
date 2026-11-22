"""The confirmatory analysis, as prereg sections 1, 5 and 6 fix it (T40), from the cached
runs/confirm-<agent>/ with no model call.

`analyze(root, runs_dir, tests, dot)` takes the test cases and the DOT case (the caller reads
them with runner.load_test_cases), reads the frozen labels of the test cases, the DOT case's
answer (the DOT text's own reading), each agent's outputs and cost lines, and
runs/confirm/complete.json, and returns the report as one dict. `eval/` is the only package
that reads the labels.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from eval import metrics
from eval.consistency import (
    RESAMPLES,
    SEED,
    carrier_month,
    case_consistent,
    cluster_draws,
    paired_difference,
)
from eval.operating_point import PREREG, recorded_grid

AGENTS = ("naive", "cheap_strong", "system")
SYSTEM = "system"
RUN = "confirm"
DOT_ANSWERS = "data/labels/dot/answers.jsonl"
ESCALATION_COST = 2.0  # prereg section 6: 3 minutes of agent time at USD 40/hour
GAP = ("2026-07-01", "2026-07-06")  # renumbered cases the version table cannot pin down

HYPOTHESES = {
    "H1": {
        "name": "Consistency share",
        "against": ("naive", "cheap_strong"),
        "criterion": "every 95% interval of system minus the other agent entirely above 0",
    },
    "H2": {
        "name": "Critical errors per 100 runs",
        "against": ("naive", "cheap_strong"),
        "criterion": "every 95% interval of system minus the other agent entirely below 0",
    },
    "H3": {
        "name": "Adversarial change share (per run)",
        "against": ("naive",),
        "criterion": "the 95% interval of system minus naive entirely below 0",
    },
}


class NotComplete(Exception):
    """The confirmatory run cannot be reported: no complete.json, or an agent's run is
    missing (report.confirm exits 2)."""


def mapped(out):
    """Prereg section 5, the decision mapping rule: a run that ends in an error, a timeout or
    a network failure (or gives no readable decision) maps to escalate."""
    d = out.get("decision")
    if (
        out.get("network_error")
        or out.get("error")
        or out.get("parse_error")
        or d not in metrics.DECISIONS
    ):
        return "escalate"
    return d


def renumbered(case):
    fact = (case.get("facts") or {}).get("renumbered") or {}
    return case.get("type") == "renumbered" or fact.get("value") is True


def exclusions(tests, labels):
    """Prereg section 6: cases with an unresolved labeling disagreement (no label) and
    renumbered cases flying 2026-07-01 to 2026-07-06; their ids and counts."""
    unlabeled = sorted(c["case_id"] for c in tests if c["case_id"] not in labels)
    gap = sorted(
        c["case_id"]
        for c in tests
        if renumbered(c) and GAP[0] <= (c.get("flight_date") or "") <= GAP[1]
    )
    out = {
        "unlabeled": {"count": len(unlabeled), "ids": unlabeled},
        "renumbered_gap": {"count": len(gap), "ids": gap},
    }
    gone = set(unlabeled) | set(gap)
    clean_gone = sorted(
        c["case_id"]
        for c in tests
        if c["case_id"] not in gone and c.get("clean_case_id") in gone
    )
    out["adversarial_clean_excluded"] = {"count": len(clean_gone), "ids": clean_gone}
    return out, gone, set(clean_gone)


def _by_case(outputs):
    d = defaultdict(list)
    for o in sorted(outputs, key=lambda o: (o["case_id"], o.get("run", 0))):
        d[o["case_id"]].append(o["decision"])
    return d


def _cost_lines(run_dir):
    path = Path(run_dir) / "costs.jsonl"
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def units(cases, labels, decisions, adversarial):
    """Per carrier-month cluster, (sum, count) of each primary outcome for one agent:
    H1 over cases, H2 (scaled to per 100), wrong and missed over case-runs, H3 over the
    adversarial case-runs; and the H3 point value, averaged over the adversarial cases."""
    h1, h2, wrong, missed, h3 = (defaultdict(lambda: [0, 0]) for _ in range(5))
    shares = []
    for c in cases:
        runs = decisions.get(c["case_id"], [])
        if not runs:
            continue
        k = carrier_month(c)
        h1[k][0] += case_consistent(runs)
        h1[k][1] += 1
        for d in runs:
            kind = metrics.classify(d, labels[c["case_id"]]["decision"])
            for u, hit in (
                (h2, kind in ("wrong", "missed")),
                (wrong, kind == "wrong"),
                (missed, kind == "missed"),
            ):
                u[k][0] += 100 * hit
                u[k][1] += 1
        if c["case_id"] in adversarial:
            clean = decisions.get(c["clean_case_id"], [])
            if not clean:
                continue
            mode = metrics.modal_or_escalate(clean)
            changed = sum(d != mode for d in runs)
            h3[k][0] += changed
            h3[k][1] += len(runs)
            shares.append(changed / len(runs))
    point = sum(shares) / len(shares) if shares else None
    return {"H1": h1, "H2": h2, "wrong": wrong, "missed": missed, "H3": h3}, point


def _value(u):
    n = sum(v[1] for v in u.values())
    return sum(v[0] for v in u.values()) / n if n else None


def primary(agents, per_agent, h3_points, resamples=RESAMPLES, seed=SEED):
    """The three hypotheses: each agent's value, the paired differences (system minus the
    other agent) with their 95% intervals, and the verdict by the prereg's criterion."""
    main_keys = sorted({k for a in agents for k in per_agent[a]["H1"]})
    adv_keys = sorted({k for a in agents for k in per_agent[a]["H3"]})
    draws = {
        "H1": cluster_draws(main_keys, resamples, seed),
        "H3": cluster_draws(adv_keys, resamples, seed) if adv_keys else [],
    }
    draws["H2"] = draws["H1"]
    out = {}
    for h, spec in HYPOTHESES.items():
        keys = adv_keys if h == "H3" else main_keys

        def full(a, h=h, keys=keys):
            u = per_agent[a][h]
            return {k: tuple(u.get(k, (0, 0))) for k in keys}

        values = {
            a: (h3_points[a] if h == "H3" else _value(per_agent[a][h])) for a in agents
        }
        comps = []
        for other in spec["against"]:
            if SYSTEM not in agents or other not in agents or not draws[h]:
                continue
            point = (
                values[SYSTEM] - values[other]
                if None not in (values[SYSTEM], values[other])
                else None
            )
            comps.append(
                {
                    "other": other,
                    **paired_difference(full(SYSTEM), full(other), draws[h], point),
                }
            )
        for c in comps:
            c["meets_criterion"] = c["low"] > 0 if h == "H1" else c["high"] < 0
        ok = len(comps) == len(spec["against"]) and all(
            c["meets_criterion"] for c in comps
        )
        out[h] = {
            "name": spec["name"],
            "criterion": spec["criterion"],
            "values": values,
            "comparisons": comps,
            "verdict": "confirmed" if ok else "not confirmed",
            "clusters": len(keys),
        }
    out["H2"]["wrong_decisions_per_100"] = {
        a: _value(per_agent[a]["wrong"]) for a in agents
    }
    out["H2"]["missed_escalations_per_100"] = {
        a: _value(per_agent[a]["missed"]) for a in agents
    }
    return out


def dot_report(dot, answers, outputs_by_agent):
    """The DOT case alone, per agent: its runs, decisions, correct runs against the DOT
    text's own reading, and whether its runs agree."""
    out = []
    for c in dot:
        cid = c["case_id"]
        answer = answers.get(cid, {}).get("answer")
        per = {}
        for a, outs in outputs_by_agent.items():
            ds = _by_case([o for o in outs if o["case_id"] == cid]).get(cid, [])
            correct = sum(d == answer for d in ds)
            per[a] = {
                "runs": len(ds),
                "decisions": dict(sorted(Counter(ds).items())),
                "correct": correct,
                "correct_share": correct / len(ds) if ds else None,
                "consistent": bool(ds) and bool(case_consistent(ds)),
            }
        out.append({"case_id": cid, "correct_answer": answer, "agents": per})
    return out


def analyze(root, runs_dir, tests, dot, agents=AGENTS, resamples=RESAMPLES, seed=SEED):
    """The confirmatory report as a dict (see report.confirm for the page)."""
    root, runs_dir = Path(root), Path(runs_dir)
    done = runs_dir / RUN / "complete.json"
    if not done.exists():
        raise NotComplete(f"no {done}: the confirmatory run is not complete")
    run = json.loads(done.read_text())
    labels = {x["case_id"]: x for x in metrics.read_jsonl(root / metrics.LABELS)}
    answers_path = root / DOT_ANSWERS
    answers = (
        {x["case_id"]: x for x in metrics.read_jsonl(answers_path)}
        if answers_path.exists()
        else {}
    )
    table = yaml.safe_load((root / "rules/versions.yaml").read_text())
    ent = yaml.safe_load(metrics.ENTITLEMENTS.read_text())
    test_ids = {c["case_id"] for c in tests}
    labels = {k: v for k, v in labels.items() if k in test_ids}
    excl, gone, clean_gone = exclusions(tests, labels)
    included = [c for c in tests if c["case_id"] not in gone]
    inc_ids = {c["case_id"] for c in included}
    adversarial = {
        c["case_id"]
        for c in included
        if c.get("clean_case_id") and c["case_id"] not in clean_gone
    }
    dollars = run.get("dollars")

    report = {
        "run": {
            "date": run.get("date"),
            "tag": run.get("tag"),
            "tag_commit": run.get("tag_commit"),
            "test_hash": run.get("test_hash"),
            "model": run.get("model"),
            "dollars": dollars,
        },
        "agents": list(agents),
        "incomplete": {},
        "invalid": [],
        "exclusions": excl,
        "cases": len(included),
        "resamples": resamples,
        "seed": seed,
    }
    per_agent, h3_points, secondary, by_type, by_airline = {}, {}, {}, {}, {}
    cost_view, accuracy, response_models, dot_outs, errors = {}, [], {}, {}, {}
    for a in agents:
        d = runs_dir / f"{RUN}-{a}"
        raw = metrics.load_outputs(d) if (d / "outputs").is_dir() else []
        if not raw:
            raise NotComplete(f"no outputs in {d}")
        failed = metrics.network_failures(raw)
        if failed:
            report["incomplete"][a] = failed
        if metrics.invalid(raw):
            report["invalid"].append(a)
        outs = [{**o, "decision": mapped(o)} for o in raw]
        errors[a] = {
            "network_errors": failed,
            "parse_errors": sum(bool(o.get("parse_error")) for o in raw),
            "mapped_to_escalate": sum(
                mapped(o) == "escalate" and o.get("decision") != "escalate" for o in raw
            ),
        }
        test_outs = [o for o in outs if o["case_id"] in inc_ids]
        dot_outs[a] = [o for o in outs if o["case_id"] in {c["case_id"] for c in dot}]
        spent = (
            dollars.get(a)
            if isinstance(dollars, dict) and a in dollars
            else metrics.load_cost_total(d)
        )
        m = metrics.agent_metrics(
            included,
            labels,
            test_outs,
            table,
            ent,
            spent,
            mode=metrics.modal_or_escalate,
            latency=metrics.latency_per_answer(d),
        )
        secondary[a], by_type[a] = m["overall"], m["by_type"]
        by_airline[a] = {
            carrier: metrics.agent_metrics(
                [c for c in included if c["carrier"] == carrier],
                labels,
                test_outs,
                table,
                ent,
                mode=metrics.modal_or_escalate,
            )["overall"]
            for carrier in sorted({c["carrier"] for c in included})
        }
        decisions = _by_case(test_outs)
        per_agent[a], h3_points[a] = units(included, labels, decisions, adversarial)
        correct = m["overall"]["correct"]
        escalations = sum(o["decision"] == "escalate" for o in test_outs)
        cost_view[a] = {
            "dollars": spent,
            "correct": correct,
            "escalations": escalations,
            "cost_per_correct_decision": spent / correct if correct else None,
            "cost_per_correct_with_escalations": (
                (spent + ESCALATION_COST * escalations) / correct if correct else None
            ),
        }
        accuracy.append(
            {
                "agent": a,
                "correct_share": m["overall"]["correct_share"],
                "dollars": spent,
            }
        )
        response_models[a] = dict(
            sorted(
                Counter(
                    str(x.get("response_model") or "none") for x in _cost_lines(d)
                ).items()
            )
        )
    report["primary"] = primary(list(agents), per_agent, h3_points, resamples, seed)
    report["secondary"] = secondary
    report["errors"] = errors
    report["by_type"] = by_type
    report["by_airline"] = by_airline
    report["cost_view"] = {"escalation_cost": ESCALATION_COST, "agents": cost_view}
    report["accuracy_vs_dollars"] = accuracy
    report["response_models"] = response_models
    report["dot"] = dot_report(dot, answers, dot_outs)
    prereg = root / PREREG
    window, rows = (
        recorded_grid(prereg.read_text(encoding="utf-8"))
        if prereg.exists()
        else (None, [])
    )
    report["development_grid"] = {"window": window, "rows": rows}
    return report
