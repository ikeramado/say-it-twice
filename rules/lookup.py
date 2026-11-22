"""Rule versions and airline policies as data, looked up by date.

rule_for(flight_date, renumbered) -> RuleVersion | Exclusion
policy_for(carrier, purchase_date) -> PolicyVersion | Exclusion
policy_candidates(carrier, purchase_date) -> tuple[PolicyVersion, ...] | Exclusion
purchase_candidates(carrier, flight_date) -> tuple[PolicyVersion | None, ...]
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "rules"

GAP_FIRST = date(2026, 7, 1)
GAP_LAST = date(2026, 7, 6)
STUDY_START = date(2024, 1, 1)


@dataclass(frozen=True)
class Clause:
    id: str
    section: str
    topic: str
    text: str
    source_file: str


@dataclass(frozen=True)
class RuleVersion:
    id: str
    first_day: date
    last_day: date | None
    clauses: tuple[Clause, ...]
    source_file: str
    source_files: tuple[str, ...]
    follows: str | None = None


@dataclass(frozen=True)
class PolicyVersion:
    id: str
    carrier: str
    carrier_date: date
    coverage: tuple[tuple[date, date | None], ...]
    clauses: tuple[Clause, ...]
    source_file: str


@dataclass(frozen=True)
class Exclusion:
    reason: str


def _d(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def _clauses(rows) -> tuple[Clause, ...]:
    return tuple(Clause(**r) for r in rows)


@cache
def rule_versions() -> tuple[RuleVersion, ...]:
    data = yaml.safe_load((RULES / "versions.yaml").read_text(encoding="utf-8"))
    out = [
        RuleVersion(
            id=v["id"],
            first_day=_d(v["first_day"]),
            last_day=_d(v["last_day"]),
            clauses=_clauses(v["clauses"]),
            source_file=v["source_file"],
            source_files=tuple(v["source_files"]),
            follows=v.get("follows"),
        )
        for v in data["versions"]
    ]
    return tuple(out)


@cache
def policy_versions(carrier: str) -> tuple[PolicyVersion, ...] | None:
    for path in sorted((RULES / "policies").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data["carrier"] == carrier:
            return tuple(
                PolicyVersion(
                    id=v["id"],
                    carrier=carrier,
                    carrier_date=_d(v["carrier_date"]),
                    coverage=tuple(
                        (_d(c["first"]), _d(c["last"])) for c in v["coverage"]
                    ),
                    clauses=_clauses(v["clauses"]),
                    source_file=v["source_file"],
                )
                for v in data["versions"]
            )
    return None


def rule_for(flight_date: date, renumbered: bool) -> RuleVersion | Exclusion:
    """The one rule version in force on flight_date, or why the case is excluded."""
    if GAP_FIRST <= flight_date <= GAP_LAST:
        if renumbered:
            return Exclusion(
                "renumbered-flight case in 2026-07-01 to 2026-07-06: the first pause ended "
                "2026-06-30 and the extension starts 2026-07-07, and no official text says "
                "whether the renumbering rule was enforced in between (ADR-0001)"
            )
        versions = {v.id: v for v in rule_versions()}
        return versions["v2"]
    for v in rule_versions():
        if v.first_day <= flight_date and (
            v.last_day is None or flight_date <= v.last_day
        ):
            return v
    return Exclusion(
        f"flight date {flight_date} is before the study window ({STUDY_START})"
    )


def policy_for(carrier: str, purchase_date: date) -> PolicyVersion | Exclusion:
    """The carrier's policy version for a ticket bought on purchase_date, or why excluded."""
    versions = policy_versions(carrier)
    if versions is None:
        return Exclusion(f"unknown carrier {carrier!r}: no airline policy on file")
    for v in versions:
        for first, last in v.coverage:
            if first <= purchase_date and (last is None or purchase_date <= last):
                return v
    return Exclusion(
        f"no saved copy of {carrier}'s contract covers ticket purchases on {purchase_date} "
        "(ADR-0001, Excluded periods)"
    )


def purchase_candidates(
    carrier: str, flight_date: date
) -> tuple[PolicyVersion | None, ...]:
    """The candidates for a ticket whose purchase date is missing (ADR-0005).

    Every saved version of the carrier dated on or before flight_date, in date order, then
    None ("no saved policy", the federal rule alone): the ticket may have been bought before
    the earliest saved copy, a day no version covers. An unknown carrier gives (None,).
    """
    versions = sorted(
        (v for v in policy_versions(carrier) or () if v.carrier_date <= flight_date),
        key=lambda v: v.carrier_date,
    )
    return (*versions, None)


def policy_candidates(
    carrier: str, purchase_date: date
) -> tuple[PolicyVersion, ...] | Exclusion:
    """The versions that could have been in force for a ticket bought on purchase_date.

    A covered date gives its one version. A date in a gap (ADR-0005) gives the version that
    covers the nearest covered day before it plus every version whose carrier_date is after
    that day and on or before purchase_date, in date order. A date before any covered day
    gives the Exclusion policy_for gives.
    """
    found = policy_for(carrier, purchase_date)
    if isinstance(found, PolicyVersion):
        return (found,)
    versions = policy_versions(carrier) or ()
    before = [
        (min(last, purchase_date) if last else purchase_date, v)
        for v in versions
        for first, last in v.coverage
        if first < purchase_date
    ]
    if not before:
        return found
    day, prev = max(before, key=lambda x: x[0])
    later = sorted(
        (
            v
            for v in versions
            if day < v.carrier_date <= purchase_date and v is not prev
        ),
        key=lambda v: v.carrier_date,
    )
    return (prev, *later)
