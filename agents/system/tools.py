"""The one access point agents use for flights, rule versions and airline policies.

Serves data/clean/, rules/versions.yaml and rules/policies/; refuses everything else (default deny).
"""

from __future__ import annotations

import csv
import io
import os
from datetime import date
from pathlib import Path

from rules.lookup import (
    ROOT,
    Exclusion,
    PolicyVersion,
    RuleVersion,
    policy_candidates,
    policy_versions,
    rule_for,
    rule_versions,
)
from rules.lookup import (
    purchase_candidates as _purchase_candidates,
)

ENV = "SAY_IT_TWICE_DATA_ROOT"
ALLOWED = ("data/clean", "rules/versions.yaml", "rules/policies")


def data_root(root: str | Path | None = None) -> Path:
    return Path(root or os.environ.get(ENV) or ROOT).resolve()


def _under(path: Path, base: Path) -> bool:
    return path == base or base in path.parents


def read_data(path: str | Path, root: str | Path | None = None) -> str:
    """Read one file under the data root; the only function here that opens a file."""
    base = data_root(root)
    target = (base / path).resolve()
    if not any(_under(target, (base / a).resolve()) for a in ALLOWED):
        raise PermissionError(f"refused: {path} is outside the served paths")
    return target.read_text(encoding="utf-8")


def get_flight(
    carrier: str,
    number: int | str,
    flight_date: date | str,
    origin: str,
    root: str | Path | None = None,
) -> dict | None:
    """The clean record of one flight, or None when not found."""
    d = str(flight_date)
    try:
        text = read_data(f"data/clean/flights/{d[:7]}.csv", root)
    except FileNotFoundError:
        return None
    for row in csv.DictReader(io.StringIO(text)):
        if (
            row["carrier"] == carrier
            and row["flight_number"] == str(number)
            and row["date"] == d
            and row["origin"] == origin
        ):
            return row
    return None


def get_rule(flight_date: date, renumbered: bool) -> RuleVersion | Exclusion:
    return rule_for(flight_date, renumbered)


def get_policy(
    carrier: str, purchase_date: date
) -> PolicyVersion | tuple[PolicyVersion, ...] | Exclusion:
    """The policy version for purchase_date; in a gap, the tuple of candidates (ADR-0005)."""
    got = policy_candidates(carrier, purchase_date)
    if isinstance(got, tuple) and len(got) == 1:
        return got[0]
    return got


def all_rule_versions() -> tuple[RuleVersion, ...]:
    """Every rule version, in date order (the naive agents' prompt holds them all)."""
    return rule_versions()


def all_policy_versions(carrier: str) -> tuple[PolicyVersion, ...]:
    """Every policy version of one carrier; an unknown carrier has none."""
    return policy_versions(carrier) or ()


def purchase_candidates(
    carrier: str, flight_date: date
) -> tuple[PolicyVersion | None, ...]:
    """Candidates for a missing purchase date: versions dated by the flight, then None."""
    return _purchase_candidates(carrier, flight_date)
