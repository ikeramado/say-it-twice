"""The rule engine: a case's facts, the rule version in force and the airline policy -> a decision.

Written from rules/versions.yaml, rules/policies/ and ADR-0004's three criteria alone.
Imports nothing from `rules` (types come through agents.system.tools).

decide(facts, rule_version, policy) -> {decision, clause, rule_version, policy_version}

`facts` maps a fact name to a plain value; a name absent from it is a missing fact.
`policy` is one PolicyVersion, an Exclusion (no policy pinned: the federal rule alone
decides), or a tuple: when purchase_date is missing, every version of the carrier; when it is
known but falls in a gap no saved copy covers, the candidate versions (ADR-0005), each weighed
in turn: the same decision under all gives it, else escalate.
Readings the texts fix (see the card's Closure for the dated list):
- a cancelled flight is refunded unless the passenger accepted the alternative offered;
- a delay is refunded when the arrival delay reaches the lowest threshold among the federal
  rule (180 min, v1 to v4) and the airline version (its own words: "greater than 120 minutes"
  is 121 and up, "3 or more hours" is 180 and up): a contract may give more than the rule;
- a renumbered flight is a cancelled flight under v2 (89 FR 32770), the pause of v3 and v4
  spares it only with no significant change, and an airline sentence "a flight number change
  is considered a cancellation" makes it a refund;
- v0 has no threshold and v0/v1 do not say whether a renumbered flight is cancelled: with no
  airline threshold to rest on the engine escalates instead of guessing.
"""

from __future__ import annotations

import itertools
import re

from agents.system.tools import (
    Exclusion,
    PolicyVersion,
    RuleVersion,
    all_policy_versions,
    all_rule_versions,
)

CARRIERS = ("DL", "AA")
FEDERAL_MINUTES = 180
HUGE = 10**6
FN_CHANGE = "flight number change is considered a cancellation"

_DELAY_PATTERNS = (
    # (regex, minutes per unit, strict)
    (r"delay of greater than (\d+) minutes", 1, True),
    (r"arrive (\d+) minutes or more after", 1, False),
    (
        r"(?:arrival (?:is )?delayed|delays your arrival) more than (\d+) hours",
        60,
        True,
    ),
    (r"delayed for (\d+) or more hours \(domestic\)", 60, False),
)


def _rules() -> dict[str, RuleVersion]:
    return {v.id: v for v in all_rule_versions()}


def _rule_clause(rule: RuleVersion, topic: str) -> str | None:
    """The id of the clause of `topic` in this rule version, or in the one it follows."""
    by_id = _rules()
    r: RuleVersion | None = rule
    while r is not None:
        for c in r.clauses:
            if c.topic == topic:
                return c.id
        r = by_id.get(r.follows) if r.follows else None
    return None


def _delay_match(text: str):
    for rx, unit, strict in _DELAY_PATTERNS:
        m = re.search(rx, text)
        if m:
            return int(m.group(1)) * unit, strict
    return None


def _policy_clause(pol: PolicyVersion) -> str | None:
    """The airline's cancellation and delay clause: the one that states a delay threshold."""
    for c in pol.clauses:
        if _delay_match(c.text):
            return c.id
    return None


def _fn_change_clause(pol: PolicyVersion) -> str | None:
    for c in pol.clauses:
        if FN_CHANGE in c.text:
            return c.id
    return None


def topic_clause(pol: PolicyVersion) -> str | None:
    """The airline clause without its version, e.g. DL-19A-schedule-change."""
    cid = _policy_clause(pol)
    if cid is None:
        return None
    return f"{pol.carrier}-{cid[len(pol.id) + 1 :]}"


def _policy_threshold(pol: PolicyVersion) -> tuple[int, int] | None:
    """(nominal minutes, least delay that is refunded) read from the airline's own words."""
    for c in pol.clauses:
        m = _delay_match(c.text)
        if m:
            n, strict = m
            return n, n + 1 if strict else n
    return None


def _federal_threshold(rule: RuleVersion) -> tuple[int, int] | None:
    return None if rule.id == "v0" else (FEDERAL_MINUTES, FEDERAL_MINUTES)


def _sources(rule: RuleVersion, pol: PolicyVersion | None):
    """Delay sources as (nominal, least refunded delay, clause id), airline first on a tie."""
    out = []
    if pol is not None:
        t = _policy_threshold(pol)
        if t:
            out.append((t[0], t[1], _policy_clause(pol)))
    t = _federal_threshold(rule)
    if t:
        out.append(
            (
                t[0],
                t[1],
                _rule_clause(rule, "delay-definition") or _rule_clause(rule, "delay"),
            )
        )
    return sorted(out, key=lambda s: s[1])


def _cancel_clause(rule: RuleVersion, pol: PolicyVersion | None) -> str | None:
    if pol is not None and _policy_clause(pol):
        return _policy_clause(pol)
    return (
        _rule_clause(rule, "refund")
        or _rule_clause(rule, "cancelled")
        or _rule_clause(rule, "policy-refunds")
    )


def _pause_clause(rule: RuleVersion) -> str | None:
    return _rule_clause(rule, "pause-renumbered") or _rule_clause(
        rule, "pause-extension"
    )


def _delay_path(
    f: dict, rule: RuleVersion, pol: PolicyVersion | None, fallback: str | None
):
    """(decision, clause) from the arrival delay alone."""
    src = _sources(rule, pol)
    if not src:
        return "escalate", fallback or _cancel_clause(rule, pol)
    delay = f["arrival_delay_min"]
    if delay >= src[0][1]:
        return "refund", src[0][2]
    return "no_refund", src[0][2]


def _core(
    f: dict, rule: RuleVersion, pol: PolicyVersion | None
) -> tuple[str, str | None]:
    cancelled = bool(f.get("cancelled"))
    if f.get("renumbered") and not cancelled:
        fn = _fn_change_clause(pol) if pol is not None else None
        if fn:
            return "refund", fn
        if rule.id == "v2":
            return "refund", _rule_clause(rule, "cancelled")
        if rule.id in ("v3", "v4"):
            if f.get("significant_change"):
                return "refund", _pause_clause(rule)
            d, c = _delay_path(f, rule, pol, None)
            return (
                ("refund", c) if d == "refund" else ("no_refund", _pause_clause(rule))
            )
        # v0, v1: whether a renumbered flight is cancelled is not in the texts
        if f.get("significant_change"):
            return "refund", _cancel_clause(rule, pol)
        d, c = _delay_path(f, rule, pol, _cancel_clause(rule, pol))
        return (d, c) if d == "refund" else ("escalate", _cancel_clause(rule, pol))
    if cancelled:
        d = "no_refund" if f.get("alternative_accepted") else "refund"
        return d, _cancel_clause(rule, pol)
    return _delay_path(f, rule, pol, None)


def _candidates(facts: dict, rule: RuleVersion, policy) -> dict[str, list]:
    """For each missing fact that could matter: the values it may take."""
    out: dict[str, list] = {}
    if "cancelled" not in facts:
        out["cancelled"] = [True, False]
    if "arrival_delay_min" not in facts and not facts.get("cancelled"):
        out["arrival_delay_min"] = [0, HUGE]
    if (
        "alternative_accepted" not in facts
        and facts.get("alternative_offered") is not False
    ):
        out["alternative_accepted"] = [True, False]
    if "significant_change" not in facts and facts.get("renumbered"):
        out["significant_change"] = [True, False]
    if "purchase_date" not in facts and isinstance(policy, tuple) and policy:
        out["purchase_date"] = list(policy)
    return out


def _evaluate(
    facts: dict, rule: RuleVersion, policy, assign: dict
) -> tuple[str, str | None]:
    f = {k: v for k, v in facts.items()}
    pol = policy if isinstance(policy, PolicyVersion) else None
    for k, v in assign.items():
        if k == "purchase_date":
            pol = v
        else:
            f[k] = v
    f.setdefault("arrival_delay_min", 0)
    return _core(f, rule, pol)


def _combos(cands: dict):
    names = list(cands)
    for vals in itertools.product(*(cands[n] for n in names)):
        yield dict(zip(names, vals))


def _gap(facts: dict, policy) -> bool:
    """A known purchase date with candidate versions (a policy gap, ADR-0005)."""
    return isinstance(policy, tuple) and "purchase_date" in facts


def missing_facts(facts: dict, rule_version, policy) -> list[str]:
    """Names of the missing facts whose value would change the decision (ADR-0004, 2 and 3)."""
    if isinstance(rule_version, Exclusion) or "request_kind" in facts:
        return []
    if _gap(facts, policy):
        out: list[str] = []
        for p in policy:
            for n in missing_facts(facts, rule_version, p):
                if n not in out:
                    out.append(n)
        return out
    cands = _candidates(facts, rule_version, policy)
    out = []
    for name in cands:
        others = {k: v for k, v in cands.items() if k != name}
        for base in _combos(others):
            res = {
                _evaluate(facts, rule_version, policy, {**base, name: v})[0]
                for v in cands[name]
            }
            if len(res) > 1:
                out.append(name)
                break
    return out


def thresholds(facts: dict, rule_version, policy) -> list[int]:
    """Nominal delay threshold(s) in minutes that decide the case: [] for a cancelled flight,
    an excluded rule or a rule with none; more than one when purchase_date is missing."""
    if isinstance(rule_version, Exclusion) or facts.get("cancelled"):
        return []
    if isinstance(policy, tuple):
        pols = list(policy)
    else:
        pols = [policy if isinstance(policy, PolicyVersion) else None]
    out = []
    for p in pols or [None]:
        src = _sources(rule_version, p)
        if src and src[0][0] not in out:
            out.append(src[0][0])
    return out


def _ids(rule, policy):
    pv = policy.id if isinstance(policy, PolicyVersion) else None
    return (None if isinstance(rule, Exclusion) else rule.id), pv


def decide(facts: dict, rule_version, policy) -> dict:
    rid, pid = _ids(rule_version, policy)

    def out(decision, clause):
        return {
            "decision": decision,
            "clause": clause,
            "rule_version": rid,
            "policy_version": pid,
        }

    if isinstance(rule_version, Exclusion):
        return out("escalate", "excluded_rule")
    if "request_kind" in facts:
        return out("escalate", "out_of_scope")
    if _gap(facts, policy) and policy:
        each = [decide(facts, rule_version, p) for p in policy]
        gid = ";".join(p.id for p in policy if p) or None
        first = each[0]["decision"]
        for r in each:
            if r["decision"] != first:
                return {**out("escalate", r["clause"]), "policy_version": gid}
        return {**out(first, each[0]["clause"]), "policy_version": gid}
    cands = _candidates(facts, rule_version, policy)
    if cands:
        results = [_evaluate(facts, rule_version, policy, a) for a in _combos(cands)]
        if len({d for d, _ in results}) > 1:
            if "purchase_date" in missing_facts(facts, rule_version, policy):
                first = next((p for p in cands["purchase_date"] if p), None)
                top = topic_clause(first) if first else None
                if top:
                    return out("escalate", top)
            for d, c in results:
                if d == "refund":
                    return out("escalate", c)
            return out("escalate", results[0][1])
        decisions = {d for d, _ in results}
        clauses = {c for _, c in results}
        d = decisions.pop()
        if len(clauses) == 1:
            return out(d, clauses.pop())
        fed = _evaluate(
            facts,
            rule_version,
            Exclusion("federal alone"),
            {k: v[0] for k, v in cands.items() if k != "purchase_date"},
        )
        return out(d, fed[1] if fed[0] == d else results[0][1])
    pol = policy if isinstance(policy, PolicyVersion) else None
    f = dict(facts)
    f.setdefault("arrival_delay_min", 0)
    d, c = _core(f, rule_version, pol)
    return out(d, c)


def _all_clauses() -> tuple[str, ...]:
    ids = ["excluded_rule", "out_of_scope"]
    for r in all_rule_versions():
        for topic in (
            "policy-refunds",
            "refund",
            "delay-definition",
            "cancelled",
            "delay",
            "pause-renumbered",
            "pause-extension",
        ):
            for c in r.clauses:
                if c.topic == topic and c.id not in ids:
                    ids.append(c.id)
    for carrier in CARRIERS:
        for p in all_policy_versions(carrier):
            for cid in (_policy_clause(p), _fn_change_clause(p), topic_clause(p)):
                if cid and cid not in ids:
                    ids.append(cid)
    return tuple(ids)


CLAUSES = _all_clauses()
