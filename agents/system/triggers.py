"""Fixed escalation triggers, written from ADR-0004's three criteria and the rule texts.

check(facts, rule_version, policy, window_minutes, amount_threshold) -> list of reasons:
`missing_fact:<name>` (a missing fact that changes the answer under some candidate version),
`boundary` (arrival delay within window_minutes of the threshold that decides the case),
`amount` (an `amount` fact over the threshold), `out_of_scope` (a `request_kind` request),
`excluded_rule` (the rule version is an Exclusion; the only reason then).
A policy Exclusion gives no reason: the federal rule alone decides.
"""

from __future__ import annotations

from agents.system import engine
from agents.system.tools import Exclusion


def check(
    facts: dict,
    rule_version,
    policy,
    window_minutes: int,
    amount_threshold: float,
) -> list[str]:
    if isinstance(rule_version, Exclusion):
        return ["excluded_rule"]
    reasons = [
        f"missing_fact:{n}" for n in engine.missing_facts(facts, rule_version, policy)
    ]
    delay = facts.get("arrival_delay_min")
    near = delay is not None and any(
        abs(delay - t) <= window_minutes
        for t in engine.thresholds(facts, rule_version, policy)
    )
    if near:
        reasons.append("boundary")
    amount = facts.get("amount")
    if amount is not None and amount > amount_threshold:
        reasons.append("amount")
    if "request_kind" in facts:
        reasons.append("out_of_scope")
    return reasons
