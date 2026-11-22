"""Decide one case from its facts and the texts. Pure functions, no engine, no I/O.

The decision is `refund` when the federal rule in force on the flight date OR the airline's
policy for the purchase date entitles the passenger to the ticket's refund (each is a promise
the passenger can hold the airline to); `no_refund` when neither does; `escalate` when a text
leaves the point open or a missing fact changes the answer.

Readings the texts leave open, and what the program does (the human's criteria of
2026-11-18, ADR-0004, plus these):
- Out-of-scope demands (`request_kind`) and the other airline cited (`cited_carrier`) change
  nothing: the ticket decision is the clean case's, under the case's own airline.
- A missing fact enumerates its possible values; if every completion and every airline
  version that could apply gives the same decision, that is the answer; if not, escalate,
  citing the airline clause whose versions differ (or, if none differs, the airline clause
  on the missing point).
- Every BTS flight is domestic, so the domestic thresholds are read.
- Accepting the offered alternative uses the ticket: no refund under any text.
- A delay under the figure of the only text in force (v1 says "at a minimum" 3 hours) is read
  as not entitling: no text grants it. Under v0, which has no figure, a delay at or above the
  next version's figure is open (escalate); below it, no text reaches it.
- A renumbered flight with no significant change before v2 (v0, v1): no text says if the
  renumbering is a cancellation: escalate.
- A renumbered flight under the v3/v4 pause with no significant change, on an airline whose
  contract says a flight number change is a cancellation: the pause only suspends DOT's
  enforcement, the airline's own clause stands: escalate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import product

from labeler_rules import texts

DELAY_SAMPLES = (0, 150, 200, 300)  # one delay in each band between the thresholds in the texts
FLIGHT_NUMBER_CLAUSE = "flight number change is considered a cancellation"
MISSING = object()


@dataclass(frozen=True)
class Answer:
    decision: str
    clause: str
    rule_version: str
    policy_version: str
    note: str = ""


@dataclass(frozen=True)
class Verdict:
    kind: str  # refund | no_refund | open
    clause: str
    note: str = ""


def view(case: dict) -> dict:
    """The case as the sheets show it: flight record and passenger facts, nothing else."""
    facts = {k: v.get("value") for k, v in (case.get("facts") or {}).items()
             if isinstance(v, dict) and "value" in v}
    return {"carrier": case.get("carrier"), "flight_date": case.get("flight_date"),
            "facts": facts}


# --- the federal rule -------------------------------------------------------


def _delay_hit(delay: int, text: str) -> bool:
    minutes, strict = texts.delay_test(text)
    return delay > minutes if strict else delay >= minutes


def rule_verdict(ver: texts.Version, f: dict) -> Verdict:
    rc = texts.rule_clause
    if f["cancelled"]:
        clause = rc(ver.id, "cancelled") or rc(ver.id, "refund") or rc(ver.id, "policy-refunds")
        kind = "no_refund" if f["accepted"] else "refund"
        return Verdict(kind, clause["id"])
    delay_clause = rc(ver.id, "delay") or rc(ver.id, "delay-definition")
    delay = f["delay"]
    if delay_clause:
        late = _delay_hit(delay, delay_clause["text"])
    else:  # v0: no figure; the next version's figure marks where the text turns open
        ref = texts.rule_versions()["v1"].clauses["delay-definition"]
        late = _delay_hit(delay, ref["text"])
    if not f["renumbered"]:
        if delay_clause:
            return Verdict("refund" if late else "no_refund", delay_clause["id"])
        clause = rc(ver.id, "policy-refunds")["id"]
        return Verdict("open" if late else "no_refund", clause,
                       "v0 defines no significant delay" if late else "")
    significant = bool(f["significant"]) or late
    pause = next((c for t, c in ver.clauses.items() if t.startswith("pause")), None)
    cancelled_def = rc(ver.id, "cancelled")
    if pause:
        if significant:
            clause = delay_clause if late else cancelled_def
            return Verdict("refund", clause["id"])
        return Verdict("no_refund", pause["id"])
    if cancelled_def:  # v2: a renumbered flight is a cancelled flight
        return Verdict("refund", cancelled_def["id"])
    clause = rc(ver.id, "refund") or rc(ver.id, "policy-refunds")
    if significant:
        return Verdict("refund", clause["id"])
    return Verdict("open", clause["id"], "no text says a mere renumbering is a cancellation")


# --- the airline's policy ---------------------------------------------------


def _policy_topic(pol: texts.Policy, order) -> dict | None:
    for t in order:
        if t in pol.clauses:
            return pol.clauses[t]
    return None


def policy_verdict(pol: texts.Policy | None, f: dict) -> Verdict:
    if pol is None:
        return Verdict("no_refund", "")
    main = _policy_topic(pol, ("schedule-change", "delay"))
    if f["cancelled"]:
        return Verdict("no_refund" if f["accepted"] else "refund", main["id"])
    late = _delay_hit(f["delay"], main["text"])
    auto = pol.clauses.get("automatic")
    if f["renumbered"] and auto and FLIGHT_NUMBER_CLAUSE in auto["text"].lower():
        if late:
            return Verdict("refund", main["id"])
        return Verdict("open", auto["id"], "the airline deems a flight number change a cancellation")
    return Verdict("refund" if late else "no_refund", main["id"])


# --- one completed case -----------------------------------------------------


def decide_complete(ver: texts.Version, pol: texts.Policy | None, f: dict) -> Answer:
    rv = rule_verdict(ver, f)
    pv = policy_verdict(pol, f)
    pid = pol.id if pol else ""
    if rv.kind == "refund":
        return Answer("refund", rv.clause, ver.id, pid)
    if pv.kind == "refund":
        return Answer("refund", pv.clause, ver.id, pid)
    if "open" in (rv.kind, pv.kind):
        o = rv if rv.kind == "open" else pv
        return Answer("escalate", o.clause, ver.id, pid, o.note)
    return Answer("no_refund", rv.clause, ver.id, pid)


# --- missing facts ----------------------------------------------------------


def _completions(facts: dict):
    """Every complete reading of the facts: a list of dicts, plus the names that were missing."""
    g = lambda k: facts.get(k, MISSING)
    base = {"renumbered": bool(facts.get("renumbered", False))}
    options: dict[str, list] = {}
    missing = []

    def need(name, values):
        missing.append(name)
        options[name] = list(values)

    cancelled = g("cancelled")
    if cancelled is MISSING:
        need("cancelled", (True, False))
    else:
        base["cancelled"] = bool(cancelled)
    accepted = g("alternative_accepted")
    if accepted is not MISSING:
        base["accepted"] = bool(accepted)
    elif g("alternative_offered") is False:
        base["accepted"] = False
    else:
        options["accepted"] = [True, False]
    delay = g("arrival_delay_min")
    if delay is not MISSING and delay is not None:
        base["delay"] = int(delay)
    else:
        options["delay"] = list(DELAY_SAMPLES)
    sig = g("significant_change")
    if sig is not MISSING:
        base["significant"] = bool(sig)
    else:
        options["significant"] = [True, False]
    # only the facts the case turns on count as missing
    names = list(options)
    out = []
    for combo in product(*(options[n] for n in names)):
        f = {**base, **dict(zip(names, combo, strict=True))}
        out.append(f)
    return out, base, options


def _relevant_missing(base: dict, options: dict) -> list[str]:
    cancelled_opts = options.get("cancelled")
    cancelled = base.get("cancelled")
    miss = []
    if cancelled_opts:
        miss.append("cancelled")
    if "accepted" in options and (cancelled_opts or cancelled):
        miss.append("alternative_accepted")
    if "delay" in options and (cancelled_opts or not cancelled):
        miss.append("arrival_delay_min")
    if "significant" in options and base["renumbered"] and (cancelled_opts or not cancelled):
        miss.append("significant_change")
    return miss


def _differing_clause(cands: tuple, carrier: str, alt_missing: bool) -> str:
    topics = ("schedule-change",) if carrier == "DL" else ("delay", "automatic")
    for t in topics:
        have = [p for p in cands if t in p.clauses]
        if len({p.clauses[t]["text"] for p in have}) > 1:
            return have[-1].clauses[t]["id"]
    pol = cands[-1]
    order = ("automatic", "schedule-change", "delay") if alt_missing else (
        "schedule-change", "delay")
    c = _policy_topic(pol, order)
    return c["id"] if c else ""


def decide(case: dict) -> Answer:
    v = view(case)
    carrier = v["carrier"]
    try:
        flight_date = date.fromisoformat(v["flight_date"])
    except (TypeError, ValueError):
        return Answer("escalate", "", "", "", "flight date is not a date")
    facts = v["facts"]
    renumbered = bool(facts.get("renumbered", False))
    ver = texts.rule_version_on(flight_date, renumbered)
    if isinstance(ver, str):
        return Answer("escalate", "", "", "", ver)
    if not texts.policies(carrier):
        return Answer("escalate", "", ver.id, "", f"no airline policy on file for {carrier!r}")

    purchase = None
    raw = facts.get("purchase_date")
    if raw:
        try:
            purchase = date.fromisoformat(str(raw))
        except ValueError:
            purchase = None
    pol = texts.policy_on(carrier, purchase) if purchase else None
    cands = (pol,) if pol else texts.policies_possible(carrier, flight_date)

    completions, base, options = _completions(facts)
    missing = _relevant_missing(base, options)
    # a fact the case does not turn on (a cancelled flight's delay) is not a missing fact
    results = []
    for f in completions:
        f = dict(f)
        if f["cancelled"]:
            f.setdefault("delay", 0)
        f.setdefault("accepted", False)
        f.setdefault("significant", False)
        for p in cands:
            results.append((f, p, decide_complete(ver, p, f)))
    decisions = {r[2].decision for r in results}
    if len(decisions) == 1:
        rep = results[0][2]
        pid = pol.id if pol else ";".join(p.id for p in cands)
        if rep.clause.startswith(("DL-", "AA-")):
            pid = rep.policy_version
        return Answer(rep.decision, rep.clause, ver.id, pid, rep.note)
    pid = pol.id if pol else ";".join(p.id for p in cands)
    clause = _differing_clause(cands, carrier, "alternative_accepted" in missing)
    reason = "the answer depends on " + ", ".join(
        (["the purchase date"] if len(cands) > 1 else []) + missing)
    return Answer("escalate", clause, ver.id, pid, reason)
