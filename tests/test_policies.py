from datetime import date

import pytest

from rules.lookup import ROOT, Exclusion, policy_for, policy_versions


def test_policy_versions_have_sources():
    # @criterion C6
    for carrier, n in (("DL", 5), ("AA", 9)):
        vs = policy_versions(carrier)
        assert len(vs) == n
        for v in vs:
            assert v.carrier == carrier and v.carrier_date and v.coverage and v.clauses
            assert (ROOT / v.source_file).is_file()
            assert all(c.id.startswith(v.id + "-") for c in v.clauses)


@pytest.mark.parametrize(
    "carrier,d,vid",
    [
        ("DL", "2024-01-01", "DL-2023-06-22"),
        ("DL", "2024-02-29", "DL-2023-06-22"),
        ("DL", "2024-04-01", "DL-2024-03-12"),
        ("DL", "2024-10-27", "DL-2024-03-12"),
        ("DL", "2024-11-12", "DL-2024-10-28"),
        ("DL", "2025-01-31", "DL-2024-10-28"),
        ("DL", "2025-10-09", "DL-2025-10-08"),
        ("DL", "2026-08-18", "DL-2026-08-18"),
        ("DL", "2027-01-01", "DL-2026-08-18"),
        ("AA", "2024-01-31", "AA-2023-10-10"),
        ("AA", "2024-04-14", "AA-2024-04-12"),
        ("AA", "2024-11-13", "AA-2024-10-28"),
        ("AA", "2026-07-31", "AA-2026-05-12"),
        ("AA", "2026-08-13", "AA-2026-08-13"),
    ],
)
def test_covered(carrier, d, vid):
    # @criterion C6
    assert policy_for(carrier, date.fromisoformat(d)).id == vid


@pytest.mark.parametrize(
    "carrier,d",
    [
        ("DL", "2024-03-15"),
        ("DL", "2024-08-15"),
        ("DL", "2024-11-11"),
        ("DL", "2026-08-17"),
        ("DL", "2023-12-31"),
        ("AA", "2024-02-15"),
        ("AA", "2024-10-15"),
        ("AA", "2026-08-12"),
    ],
)
def test_excluded(carrier, d):
    # @criterion C6
    ex = policy_for(carrier, date.fromisoformat(d))
    assert isinstance(ex, Exclusion) and "ADR-0001" in ex.reason


def test_unknown_carrier():
    # @criterion C6
    ex = policy_for("UA", date(2026, 9, 1))
    assert isinstance(ex, Exclusion) and "UA" in ex.reason


def _cands(carrier, d):
    from rules.lookup import policy_candidates

    return policy_candidates(carrier, date.fromisoformat(d))


def test_candidates_covered_date_is_one_version():
    # @criterion C6
    assert [v.id for v in _cands("AA", "2024-04-14")] == ["AA-2024-04-12"]


@pytest.mark.parametrize(
    "carrier,d,ids",
    [
        ("AA", "2024-07-30", ["AA-2024-04-12", "AA-2024-07-25"]),
        ("AA", "2024-08-01", ["AA-2024-04-12", "AA-2024-07-25"]),
        ("AA", "2024-03-01", ["AA-2023-10-10"]),
        ("AA", "2026-03-15", ["AA-2025-06-27", "AA-2026-03-02"]),
        ("DL", "2024-08-15", ["DL-2024-03-12"]),
    ],
)
def test_candidates_in_a_gap(carrier, d, ids):
    # @criterion C6
    assert [v.id for v in _cands(carrier, d)] == ids


def test_candidates_before_any_covered_day_is_excluded():
    # @criterion C6
    ex = _cands("DL", "2023-12-31")
    assert isinstance(ex, Exclusion) and ex == policy_for("DL", date(2023, 12, 31))


def test_purchase_candidates_drop_versions_after_the_flight_and_end_with_none():
    # @criterion C6
    from rules.lookup import purchase_candidates

    got = purchase_candidates("AA", date(2024, 8, 5))
    assert [p.id if p else None for p in got] == [
        "AA-2023-10-10",
        "AA-2024-04-12",
        "AA-2024-07-25",
        None,
    ]
    assert purchase_candidates("UA", date(2024, 8, 5)) == (None,)
