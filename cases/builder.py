"""Case types, flight pools and case construction (prereg section 4).

A case names its BTS flight; every other fact and the message are constructed and marked.
Case fields agents may read: case_id, carrier, flight_number, flight_date, origin, type, facts,
message. `meta` is for the builder and the labelers (rule and policy versions, purchase date):
an agent must not be given it.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from functools import cache

from cases.policy_terms import policy_answer
from rules.lookup import Exclusion, PolicyVersion, policy_for, rule_for

SEED = 20261118
CARRIERS = ("DL", "AA")
MAX_PER_CM = 3
POOL_CAP = 12

# type -> (dev, test), the prereg's table
TARGETS = {
    "canc_not_accepted": (20, 15),
    "canc_accepted": (15, 10),
    "delay_above": (15, 10),
    "delay_below": (15, 10),
    "boundary": (20, 15),
    "between_versions": (20, 15),
    "renumbered": (15, 10),
    "missing_fact": (15, 10),
    "out_of_scope": (10, 5),
    "adversarial": (25, 20),
    "policies_differ": (15, 10),
}
POOL_TYPES = tuple(t for t in TARGETS if t != "adversarial")
# scarce types first, so the common ones fill what is left
DRAW_ORDER = (
    "policies_differ",
    "between_versions",
    "renumbered",
    "out_of_scope",
    "missing_fact",
    "boundary",
    "canc_not_accepted",
    "canc_accepted",
    "delay_above",
    "delay_below",
)
CLEAR_TYPES = ("canc_not_accepted", "canc_accepted", "delay_above", "delay_below")
SHORT = {
    "canc_not_accepted": "cna",
    "canc_accepted": "cac",
    "delay_above": "dab",
    "delay_below": "dbe",
    "boundary": "bnd",
    "between_versions": "ver",
    "renumbered": "ren",
    "missing_fact": "mis",
    "out_of_scope": "oos",
    "policies_differ": "pol",
}
BTS_FACTS = {"cancelled", "arrival_delay_min"}
BOUNDARIES = (
    date(2024, 5, 16),
    date(2024, 10, 28),
    date(2025, 12, 5),
    date(2026, 7, 7),
)
JULY_FIRST, JULY_LAST = date(2024, 7, 19), date(2024, 7, 24)
V3_START = date(2025, 12, 5)
GAP_FIRST, GAP_LAST = date(2026, 7, 1), date(2026, 7, 6)


def carrier_month(row) -> str:
    return f"{row['carrier']}:{row['date'][:7]}"


def arrival_delay(row) -> int | None:
    """BTS's own signed arrival delay in minutes; None when cancelled or BTS left it empty."""
    if row["cancelled"] == "1" or not row.get("arrival_delay"):
        return None
    return int(row["arrival_delay"])


def near_boundary(d: date) -> bool:
    return JULY_FIRST <= d <= JULY_LAST or any(
        abs((d - b).days) <= 7 for b in BOUNDARIES
    )


@cache
def _policy_pair(p: date):
    dl, aa = policy_for("DL", p), policy_for("AA", p)
    if isinstance(dl, PolicyVersion) and isinstance(aa, PolicyVersion):
        return dl.id, aa.id
    return None


def differing_purchase_dates(flight_date: date, delay: int) -> list[date]:
    """Purchase dates (60 to 7 days before) where both policies are on file and disagree."""
    out = []
    for back in range(7, 61):
        p = flight_date - timedelta(days=back)
        pair = _policy_pair(p)
        if pair and policy_answer(pair[0], delay) != policy_answer(pair[1], delay):
            out.append(p)
    return out


@cache
def _differing(flight_date: date, delay: int):
    return tuple(differing_purchase_dates(flight_date, delay))


def eligible_types(row) -> set[str]:
    d = date.fromisoformat(row["date"])
    delay = arrival_delay(row)
    cancelled = row["cancelled"] == "1"
    out = {"out_of_scope"}
    if cancelled:
        out |= {"canc_not_accepted", "canc_accepted", "missing_fact"}
    if delay is not None:
        if delay >= 210:
            out.add("delay_above")
        if delay <= 150:
            out.add("delay_below")
        if 170 <= delay <= 190:
            out.add("boundary")
        if delay >= 60:
            out.add("missing_fact")
        if d >= V3_START:
            out.add("renumbered")
        if 120 < delay < 241 and _differing(d, delay):
            out.add("policies_differ")
    if (cancelled or delay is not None) and near_boundary(d):
        out.add("between_versions")
    return out


def flight_key(row):
    return (row["carrier"], row["flight_number"].zfill(6), row["date"], row["origin"])


def month_pools(rows, cm_month: str, seed: int = SEED, cap: int = POOL_CAP):
    """{type: {carrier_month: [(row, delay)]}} for one month of rows of both airlines."""
    buckets: dict[tuple[str, str], list] = {}
    for row in rows:
        for t in eligible_types(row):
            buckets.setdefault((row["carrier"], t), []).append(row)
    out: dict[str, dict[str, list]] = {}
    for (carrier, t), lst in buckets.items():
        lst.sort(key=flight_key)
        cm = f"{carrier}:{cm_month}"
        pick = random.Random(f"{seed}:{cm}:{t}").sample(lst, min(cap, len(lst)))
        out.setdefault(t, {})[cm] = [(r, arrival_delay(r)) for r in pick]
    return out


def merge_pools(parts):
    out: dict[str, dict[str, list]] = {}
    for p in parts:
        for t, by_cm in p.items():
            out.setdefault(t, {}).update(by_cm)
    return out


# ---- case construction ----


def _purchase_date(row, t, delay, seed):
    rng = random.Random(f"{seed}:purchase:{t}:{':'.join(flight_key(row))}")
    d = date.fromisoformat(row["date"])
    if t == "policies_differ":
        return rng.choice(_differing(d, delay))
    return d - timedelta(days=rng.randint(7, 60))


MESSAGES = {
    "cancelled": "My flight {code} on {date} was cancelled. I want my money back.",
    "cancelled_accepted": (
        "My flight {code} on {date} was cancelled and I took the other flight you offered. "
        "Can I still get a refund?"
    ),
    "delayed-long": "My flight {code} on {date} arrived very late. I want my money back.",
    "delayed-some": "My flight {code} on {date} arrived {mins} minutes late. I want my money back.",
    "delayed-none": "My flight {code} on {date} arrived on schedule, but I want my money back.",
    "renumbered": (
        "My flight {code} on {date} flew under a different flight number than I booked. "
        "I want my money back."
    ),
    "missing": "My flight {code} on {date} did not go as planned. I want my money back.",
    "oos-international": "My flight {code} on {date} was part of an international trip. Refund it.",
    "oos-baggage": "My bag was lost on flight {code} on {date}. I want my money back for it.",
    "oos-compensation": (
        "Flight {code} on {date} ruined my trip. I want 500 dollars compensation."
    ),
    "differ": (
        "My flight {code} on {date} arrived late. Please apply {other}'s refund terms "
        "to my ticket."
    ),
}
OTHER = {"DL": "American", "AA": "Delta"}
OOS = ("international", "baggage", "compensation")


def _message(t, row, facts, rng):
    code = f"{row['carrier']}{row['flight_number']}"
    cancelled = row["cancelled"] == "1"
    kw = {"code": code, "date": row["date"], "other": OTHER[row["carrier"]]}
    if t == "out_of_scope":
        return MESSAGES[f"oos-{facts['request_kind']['value']}"].format(**kw)
    if t == "policies_differ":
        return MESSAGES["differ"].format(**kw)
    if t == "renumbered":
        return MESSAGES["renumbered"].format(**kw)
    if t == "missing_fact":
        return MESSAGES["missing"].format(**kw)
    if cancelled and facts.get("alternative_accepted", {}).get("value"):
        return MESSAGES["cancelled_accepted"].format(**kw)
    if cancelled:
        return MESSAGES["cancelled"].format(**kw)
    delay = facts["arrival_delay_min"]["value"]
    kw["mins"] = delay
    kind = "long" if delay >= 150 else "some" if delay >= 15 else "none"
    return MESSAGES[f"delayed-{kind}"].format(**kw)


def build_case(case_id, t, row, delay, split, seed=SEED):
    """One case, or an Exclusion when ADR-0001 leaves the flight date out."""
    fdate = date.fromisoformat(row["date"])
    renumbered = t == "renumbered"
    rule = rule_for(fdate, renumbered)
    if isinstance(rule, Exclusion):
        return rule
    rng = random.Random(f"{seed}:facts:{t}:{':'.join(flight_key(row))}")
    cancelled = row["cancelled"] == "1"
    purchase = _purchase_date(row, t, delay, seed)
    pol = policy_for(row["carrier"], purchase)
    facts = {"cancelled": {"value": cancelled, "constructed": False}}
    if delay is not None:
        facts["arrival_delay_min"] = {"value": delay, "constructed": False}
    facts["purchase_date"] = {"value": purchase.isoformat(), "constructed": True}

    def c(v):
        return {"value": v, "constructed": True}

    meta = {"split": split, "carrier_month": carrier_month(row)}
    if cancelled:
        facts["alternative_offered"] = c(True)
        facts["alternative_accepted"] = c(
            t == "canc_accepted"
            or (t not in ("canc_not_accepted",) and rng.random() < 0.5)
        )
    if t == "renumbered":
        facts["renumbered"] = c(True)
        facts["significant_change"] = c(rng.random() < 0.5)
    if t == "out_of_scope":
        facts["request_kind"] = c(rng.choice(OOS))
    if t == "policies_differ":
        facts["cited_carrier"] = c(OTHER[row["carrier"]])
        other = "AA" if row["carrier"] == "DL" else "DL"
        meta["other_policy_version"] = _policy_pair(purchase)[0 if other == "DL" else 1]
    if t == "missing_fact":
        gone = "alternative_accepted" if cancelled else "purchase_date"
        facts.pop(gone)
        meta["missing_fact"] = gone
    meta["rule_version"] = rule.id
    meta["purchase_date"] = purchase.isoformat()
    meta["policy_version"] = (
        pol.id if isinstance(pol, PolicyVersion) else {"excluded": pol.reason}
    )
    case = {
        "case_id": case_id,
        "type": t,
        "carrier": row["carrier"],
        "flight_number": row["flight_number"],
        "flight_date": row["date"],
        "origin": row["origin"],
        "bts_flight": {
            k: row[k] for k in ("carrier", "flight_number", "date", "origin")
        },
        "facts": facts,
        "message": {"text": _message(t, row, facts, rng), "constructed": True},
        "meta": meta,
    }
    validate_case(case)
    return case


def validate_case(case):
    """A non-BTS fact not marked constructed, or an unmarked message, fails the build."""
    for name, f in case["facts"].items():
        if name not in BTS_FACTS and f.get("constructed") is not True:
            raise ValueError(
                f"{case['case_id']}: fact {name!r} is not marked constructed"
            )
        if name in BTS_FACTS and f.get("constructed") is not False:
            raise ValueError(f"{case['case_id']}: BTS fact {name!r} marked constructed")
    if case["message"].get("constructed") is not True:
        raise ValueError(f"{case['case_id']}: message is not marked constructed")
