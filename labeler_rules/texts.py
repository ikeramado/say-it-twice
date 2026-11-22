"""The texts as data: rule versions and airline policy versions, read straight from the YAML."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

import yaml

RULES = Path(__file__).resolve().parent.parent / "rules"
GAP = (date(2026, 7, 1), date(2026, 7, 6))  # ADR-0001: no text says whether the pause ran
STUDY_START = date(2024, 1, 1)


def _d(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


@dataclass(frozen=True)
class Version:
    id: str
    first: date
    last: date | None
    follows: str | None
    clauses: dict  # topic -> {"id", "text"}


@dataclass(frozen=True)
class Policy:
    id: str
    carrier: str
    coverage: tuple
    clauses: dict  # topic -> {"id", "text"}


def _keyed(clauses: list) -> dict:
    """Clauses by topic; by section when topics repeat (American's are all `refund`)."""
    topics = [c["topic"] for c in clauses]
    key = "topic" if len(set(topics)) == len(topics) else "section"
    return {c[key]: {"id": c["id"], "text": c["text"]} for c in clauses}


@cache
def rule_versions() -> dict[str, Version]:
    data = yaml.safe_load((RULES / "versions.yaml").read_text(encoding="utf-8"))
    return {
        v["id"]: Version(
            v["id"], _d(v["first_day"]), _d(v["last_day"]), v.get("follows"),
            {c["topic"]: {"id": c["id"], "text": c["text"]} for c in v["clauses"]},
        )
        for v in data["versions"]
    }


@cache
def policies(carrier: str) -> tuple[Policy, ...]:
    for path in sorted((RULES / "policies").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data["carrier"] == carrier:
            return tuple(
                Policy(
                    v["id"], carrier,
                    tuple((_d(c["first"]), _d(c["last"])) for c in v["coverage"]),
                    _keyed(v["clauses"]),
                )
                for v in data["versions"]
            )
    return ()


def rule_clause(version_id: str, topic: str) -> dict | None:
    """The clause of `topic` in the version, or in the version it follows (v3, v4 follow v2)."""
    seen = set()
    vid = version_id
    versions = rule_versions()
    while vid and vid not in seen:
        seen.add(vid)
        v = versions[vid]
        if topic in v.clauses:
            return v.clauses[topic]
        vid = v.follows
    return None


def rule_version_on(flight_date: date, renumbered: bool) -> Version | str:
    """The version in force on the flight date, or the reason none is pinned down."""
    versions = rule_versions()
    if GAP[0] <= flight_date <= GAP[1]:
        if renumbered:
            return "renumbered flight between the two pauses: no text says if it was enforced"
        return versions["v2"]
    for v in versions.values():
        if v.first <= flight_date and (v.last is None or flight_date <= v.last):
            return v
    return f"flight date {flight_date} is outside the versions on file"


def policy_on(carrier: str, purchase: date) -> Policy | None:
    for p in policies(carrier):
        for first, last in p.coverage:
            if first <= purchase and (last is None or purchase <= last):
                return p
    return None


def policies_possible(carrier: str, flight_date: date) -> tuple[Policy, ...]:
    """Versions that can govern a ticket for this flight: bought on or before the flight."""
    out = []
    for p in policies(carrier):
        if any(first <= flight_date for first, _ in p.coverage):
            out.append(p)
    return tuple(out)


# --- thresholds read from clause text --------------------------------------


def delay_test(text: str):
    """(minutes, strict) from a delay clause: arrival delay > minutes when strict, else >=.

    Reads the domestic figure: "3 or more hours (domestic)", "more than 4 hours",
    "greater than 120 minutes", "180 minutes or more", "3 or more hours after".
    """
    t = text.lower().replace("three hours", "3 hours").replace("six hours", "6 hours")
    t = t.replace("3 hours or more", "3 or more hours")
    m = re.search(r"greater than (\d+) minutes", t)
    if m:
        return int(m.group(1)), True
    m = re.search(r"(\d+) minutes or more", t)
    if m:
        return int(m.group(1)), False
    m = re.search(r"more than (\d+) hours", t)
    if m:
        return int(m.group(1)) * 60, True
    m = re.search(r"(\d+) or more hours", t)
    if m:
        return int(m.group(1)) * 60, False
    m = re.search(r"(?:domestic itineraries|domestic flight)[^;]*?(\d+) or more hours", t)
    if m:
        return int(m.group(1)) * 60, False
    return None
