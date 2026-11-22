"""The naive agent: every rule version and both airlines' policies in one prompt, one call.

The rule and policy texts (with the instructions) are the cached prefix; the case, through
the view, is the uncached prompt. The answer is a JSON object {decision, clause, rule_version,
policy_version, explanation}; one that does not parse, or a decision outside DECISIONS, is
recorded as escalate with parse_error true.
"""

import hashlib
import json
import re
from functools import cache
from pathlib import Path
from string import Template

from agents.system import tools
from agents.view import view
from llm.provider import agent_model

MODEL = agent_model()
CALLS_PER_CASE = 1
CARRIERS = ("AA", "DL")
DECISIONS = ("refund", "no_refund", "escalate")
FIELDS = ("decision", "clause", "rule_version", "policy_version", "explanation")
PROMPTS = Path(__file__).resolve().parent / "prompts"
SYSTEM = "naive_system.txt"
CASE = "naive_case.txt"


def _read(name):
    return (PROMPTS / name).read_text(encoding="utf-8")


def prompt_hashes():
    """SHA-256 of each prompt file, written in every trace."""
    return {
        n: hashlib.sha256((PROMPTS / n).read_bytes()).hexdigest()
        for n in (SYSTEM, CASE)
    }


def _clauses(clauses):
    return "\n".join(f"- [{c.id}] ({c.section}, {c.topic}) {c.text}" for c in clauses)


def _rule(v):
    last = v.last_day or "no end date"
    return f"### Rule version {v.id}: in force {v.first_day} to {last}\n{_clauses(v.clauses)}"


def _policy(v):
    spans = ", ".join(f"{a} to {b or 'no end date'}" for a, b in v.coverage)
    return (
        f"### Policy version {v.id} ({v.carrier}): covers tickets purchased {spans}\n"
        f"{_clauses(v.clauses)}"
    )


@cache
def prefix():
    """The cached prefix: instructions, every rule version, every policy of both airlines."""
    rules = "\n\n".join(_rule(v) for v in tools.all_rule_versions())
    policies = "\n\n".join(
        _policy(v) for c in CARRIERS for v in tools.all_policy_versions(c)
    )
    return (
        f"{_read(SYSTEM)}\n## Federal refund rule, every version\n\n{rules}\n\n"
        f"## Airline refund policies, every version of both airlines\n\n{policies}\n"
    )


def flight(v):
    """The flight record of a view, or None when the clean data has no such flight
    (or the case has no flight at all)."""
    if None in (v["carrier"], v["flight_number"], v["flight_date"], v["origin"]):
        return None
    return tools.get_flight(
        v["carrier"], v["flight_number"], v["flight_date"], v["origin"]
    )


def _record(rec):
    if rec is None:
        return "not found", "not found"
    cancelled = "yes" if rec["cancelled"] == "1" else "no"
    delay = rec["arrival_delay"]
    return cancelled, (f"{delay} minutes" if delay != "" else "not reported")


def case_prompt(v, rec):
    cancelled, delay = _record(rec)
    facts = "\n".join(f"- {k}: {json.dumps(x)}" for k, x in v["facts"].items())
    return Template(_read(CASE)).substitute(
        id=v["id"],
        carrier=v["carrier"],
        flight_number=v["flight_number"],
        flight_date=v["flight_date"],
        origin=v["origin"],
        cancelled=cancelled,
        arrival_delay=delay,
        facts=facts or "- none",
        message=v["message"],
    )


def prompt(case):
    v = view(case)
    return case_prompt(v, flight(v))


def parse(text):
    """{FIELDS..., parse_error}: the first JSON object in text, or escalate on any fault."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        obj = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        obj = None
    if not isinstance(obj, dict) or obj.get("decision") not in DECISIONS:
        return {
            "decision": "escalate",
            "clause": None,
            "rule_version": None,
            "policy_version": None,
            "explanation": "the model's answer could not be read",
            "parse_error": True,
        }
    out = {f: obj.get(f) for f in FIELDS}
    out["explanation"] = str(out["explanation"] or "")
    out["parse_error"] = False
    return out


def no_flight(v):
    return {
        "decision": "escalate",
        "clause": "no_flight",
        "rule_version": None,
        "policy_version": None,
        "explanation": "the flight is not in the clean flight records",
        "parse_error": False,
    }


def ask(v, rec, bound):
    """One call through a bound gate: (parsed answer, trace line)."""
    p = case_prompt(v, rec)
    text = bound.call(p, prefix=prefix())
    out = parse(text)
    line = {
        "id": v["id"],
        "sample": bound.sample,
        "prompts_sha256": prompt_hashes(),
        "prefix_sha256": hashlib.sha256(prefix().encode("utf-8")).hexdigest(),
        "prompt": p,
        "answer": text,
        "parse_error": out["parse_error"],
    }
    if out["parse_error"]:
        # Why the answer was unreadable, e.g. max_tokens when thinking used the budget.
        line["stop_reason"] = getattr(bound, "last_stop_reason", None)
    return out, line


def run(case, gate):
    v = view(case)
    rec = flight(v)
    if rec is None:
        out = no_flight(v)
        trace = [{"id": v["id"], "flight": "not found", "parse_error": False}]
    else:
        out, line = ask(v, rec, gate)
        trace = [line]
    return {**out, "trace": trace}
