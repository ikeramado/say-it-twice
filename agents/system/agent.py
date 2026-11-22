"""The system agent: facts by tools, the decision by the engine, only the explanation by the model.

It gathers the flight record, the rule version in force and the policy of the case's own
airline through agents.system.tools, runs the fixed triggers (config/triggers.yaml), lets the
engine decide, and asks the model for the explanation alone. The decision is the engine's, or
escalate when a trigger fires; the model's text never changes it. The explanation returned is
the model's text plus a citation the code builds, [rule_version / clause / policy_version].
"""

import hashlib
import json
from datetime import date
from pathlib import Path
from string import Template

import yaml

from agents.system import engine, tools, triggers
from agents.view import view
from llm.provider import agent_model

MODEL = agent_model()
CALLS_PER_CASE = 2
ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS = ROOT / "agents" / "prompts"
SYSTEM = "system_system.txt"
CASE = "system_case.txt"
TRIGGERS = ROOT / "config" / "triggers.yaml"


def _read(name):
    return (PROMPTS / name).read_text(encoding="utf-8")


def prompt_hashes():
    return {
        n: hashlib.sha256((PROMPTS / n).read_bytes()).hexdigest()
        for n in (SYSTEM, CASE)
    }


def trigger_params():
    return yaml.safe_load(TRIGGERS.read_text(encoding="utf-8"))


def prefix():
    return _read(SYSTEM)


def _flight_facts(rec):
    """Facts from the clean flight record: cancelled as a bool, delay absent when empty."""
    out = {"cancelled": rec["cancelled"] == "1"}
    if rec["arrival_delay"] != "":
        out["arrival_delay_min"] = int(rec["arrival_delay"])
    return out


def gather(v):
    """(facts, rule, policy, tool_calls), or None when the flight is not found."""
    calls = []
    if None in (v["carrier"], v["flight_number"], v["flight_date"], v["origin"]):
        return None
    rec = tools.get_flight(
        v["carrier"], v["flight_number"], v["flight_date"], v["origin"]
    )
    calls.append(
        {
            "tool": "get_flight",
            "args": [v["carrier"], v["flight_number"], v["flight_date"], v["origin"]],
            "found": rec is not None,
        }
    )
    if rec is None:
        return None
    facts = {
        k: x
        for k, x in v["facts"].items()
        if k not in ("cancelled", "arrival_delay_min")
    }
    facts.update(_flight_facts(rec))
    renumbered = bool(facts.setdefault("renumbered", False))
    rule = tools.get_rule(date.fromisoformat(v["flight_date"]), renumbered)
    calls.append(
        {
            "tool": "get_rule",
            "args": [v["flight_date"], renumbered],
            "result": _id(rule),
        }
    )
    if "purchase_date" in facts:
        pd = facts["purchase_date"]
        policy = tools.get_policy(v["carrier"], date.fromisoformat(pd))
        calls.append(
            {
                "tool": "get_policy",
                "args": [v["carrier"], pd],
                "result": _policy_result(policy),
            }
        )
    else:
        fd = v["flight_date"]
        policy = tools.purchase_candidates(v["carrier"], date.fromisoformat(fd))
        calls.append(
            {
                "tool": "purchase_candidates",
                "args": [v["carrier"], fd],
                "result": [p.id if p else None for p in policy],
            }
        )
    return facts, rule, policy, calls


def _policy_result(policy):
    if isinstance(policy, tuple):
        return [p.id if p else None for p in policy]
    return _id(policy)


def _id(x):
    return None if isinstance(x, tools.Exclusion) else x.id


def _policy_ids(policy):
    if isinstance(policy, tuple):
        return [p.id for p in policy if p]
    return [] if isinstance(policy, tools.Exclusion) else [policy.id]


def decide(v):
    """(result, engine result, facts, reasons, tool_calls, rule_id, policy_ids), no model call."""
    got = gather(v)
    if got is None:
        res = {
            "decision": "escalate",
            "clause": "no_flight",
            "rule_version": None,
            "policy_version": None,
        }
        return res, res, {}, [], [], None, []
    facts, rule, policy, calls = got
    eng = engine.decide(facts, rule, policy)
    res = eng
    p = trigger_params()
    reasons = triggers.check(
        facts, rule, policy, p["window_minutes"], p["amount_threshold"]
    )
    if reasons:
        res = {**res, "decision": "escalate", "clause": ",".join(reasons)}
    return res, eng, facts, reasons, calls, _id(rule), _policy_ids(policy)


def case_prompt(v, res, facts, reasons):
    return Template(_read(CASE)).substitute(
        id=v["id"],
        carrier=v["carrier"],
        flight_number=v["flight_number"],
        flight_date=v["flight_date"],
        origin=v["origin"],
        facts="\n".join(f"- {k}: {json.dumps(x)}" for k, x in facts.items())
        or "- none",
        decision=res["decision"],
        clause=res["clause"],
        triggers=", ".join(reasons) or "none",
        message=v["message"],
    )


def citation(res):
    return f"[{res['rule_version']} / {res['clause']} / {res['policy_version']}]"


def prompt(case):
    v = view(case)
    res, _, facts, reasons, *_ = decide(v)
    return case_prompt(v, res, facts, reasons)


def run(case, gate):
    v = view(case)
    res, eng, facts, reasons, calls, rule_id, policy_ids = decide(v)
    if res["clause"] == "no_flight":
        line = {"id": v["id"], "tool_calls": calls, "engine": eng, "triggers": []}
        if not calls:
            line["skipped"] = "no flight"
        return {
            **res,
            "explanation": "the flight is not in the clean flight records",
            "trace": [line],
            "parse_error": False,
        }
    p = case_prompt(v, res, facts, reasons)
    text = str(gate.call(p, prefix=prefix()) or "").strip()
    trace = [
        {
            "id": v["id"],
            "sample": gate.sample,
            "tool_calls": calls,
            "facts": facts,
            "rule_version": rule_id,
            "policy_versions": policy_ids,
            "engine": eng,
            "triggers": reasons,
            "explanation_prompt_sha256": hashlib.sha256(p.encode("utf-8")).hexdigest(),
            "prompts_sha256": prompt_hashes(),
            "prompt": p,
            "answer": text,
            "stop_reason": getattr(gate, "last_stop_reason", None),
        }
    ]
    return {
        "decision": res["decision"],
        "explanation": f"{text} {citation(res)}".strip(),
        "trace": trace,
        "clause": res["clause"],
        "rule_version": res["rule_version"],
        "policy_version": res["policy_version"],
        "parse_error": False,
    }
