import calendar
import random
from datetime import date

import pytest

from cases import builder
from cases.builder import TARGETS, build_case, merge_pools, month_pools, validate_case
from rules.lookup import Exclusion

MONTHS = [f"{y}-{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13)][:32]
_CACHE = {}


def _hhmm(mins):
    mins %= 1440
    return f"{mins // 60:02d}{mins % 60:02d}"


def synth_rows(month, carrier, n=220):
    """Synthetic clean BTS rows of one carrier-month: cancellations and every delay size."""
    rng = random.Random(f"synth:{month}:{carrier}")
    y, m = map(int, month.split("-"))
    rows = []
    for i in range(n):
        day = rng.randint(1, calendar.monthrange(y, m)[1])
        sched_dep = rng.randint(300, 1200)
        sched_arr = sched_dep + 120
        cancelled = rng.random() < 0.12
        delay = rng.choice(
            [-10, 0, 20, 60, 100, 140, 160, 175, 185, 200, 215, 260, 300]
        )
        rows.append(
            {
                "carrier": carrier,
                "flight_number": str(100 + i),
                "date": f"{month}-{day:02d}",
                "origin": "ATL",
                "destination": "JFK",
                "scheduled_departure": _hhmm(sched_dep),
                "actual_departure": ""
                if cancelled
                else _hhmm(sched_dep + max(delay, 0)),
                "scheduled_arrival": _hhmm(sched_arr),
                "actual_arrival": "" if cancelled else _hhmm(sched_arr + delay),
                "departure_delay": "" if cancelled else str(max(delay, 0)),
                "arrival_delay": "" if cancelled else str(delay),
                "cancelled": "1" if cancelled else "0",
                "diverted": "0",
                "cancellation_code": "A" if cancelled else "",
            }
        )
    return rows


def synth_pools(months=MONTHS):
    key = tuple(months)
    if key not in _CACHE:
        _CACHE[key] = merge_pools(
            month_pools(synth_rows(mo, c), mo)
            for mo in months
            for c in builder.CARRIERS
        )
    return _CACHE[key]


def test_long_delays_are_well_above_never_early():
    # @criterion C6
    for minutes in (22 * 60, 25 * 60):
        row = {**synth_rows("2024-07", "AA", 1)[0], "arrival_delay": str(minutes)}
        row.update(cancelled="0", date="2024-07-05")
        assert builder.arrival_delay(row) == minutes
        types = builder.eligible_types(row)
        assert "delay_above" in types and "delay_below" not in types
    row = {**row, "arrival_delay": ""}
    types = builder.eligible_types(row)
    assert builder.arrival_delay(row) is None
    assert not types & {"delay_above", "delay_below", "boundary", "missing_fact"}
    assert (
        builder.arrival_delay({**row, "cancelled": "1", "arrival_delay": "5"}) is None
    )


def test_types_match_conditions_and_caps():
    # @criterion C6
    from cases.split import build_split

    res = build_split(synth_pools())
    cases = res["dev"] + res["test"]
    per = {}
    for c in cases:
        t, d = c["type"], c["facts"].get("arrival_delay_min", {}).get("value")
        fd = date.fromisoformat(c["flight_date"])
        cancelled = c["facts"]["cancelled"]["value"]
        per[(t, c["meta"]["carrier_month"])] = (
            per.get((t, c["meta"]["carrier_month"]), 0) + 1
        )
        if t in ("canc_not_accepted", "canc_accepted"):
            assert cancelled and c["facts"]["alternative_offered"]["value"]
            assert c["facts"]["alternative_accepted"]["value"] == (t == "canc_accepted")
        if t == "delay_above":
            assert not cancelled and d >= 210
        if t == "delay_below":
            assert not cancelled and d <= 150
        if t == "boundary":
            assert 170 <= d <= 190
        if t == "between_versions":
            assert builder.near_boundary(fd)
        if t == "renumbered":
            assert fd >= builder.V3_START and c["facts"]["renumbered"]["value"]
            assert "significant_change" in c["facts"]
        if t == "missing_fact":
            assert c["meta"]["missing_fact"] not in c["facts"]
        if t == "out_of_scope":
            assert c["facts"]["request_kind"]["value"] in builder.OOS
        if t == "policies_differ":
            assert isinstance(c["meta"]["policy_version"], str)
            assert c["meta"]["other_policy_version"]
    assert max(per.values()) <= 3
    for side in ("dev", "test"):
        for t in TARGETS:
            carriers = {c["carrier"] for c in res[side] if c["type"] == t}
            assert carriers == {"DL", "AA"}, (side, t)


def test_seed_makes_cases_repeatable():
    # @criterion C6
    from cases.split import build_split

    a, b = build_split(synth_pools()), build_split(synth_pools())
    assert a == b
    assert builder.SEED == 20261118


def test_purchase_date_window_and_policy_layer():
    # @criterion C6
    from cases.split import build_split

    res = build_split(synth_pools())
    saw_excluded = False
    for c in res["dev"] + res["test"]:
        fd = date.fromisoformat(c["flight_date"])
        pd = date.fromisoformat(c["meta"]["purchase_date"])
        assert 7 <= (fd - pd).days <= 60
        if isinstance(c["meta"]["policy_version"], dict):
            assert c["type"] != "policies_differ"
            saw_excluded = True
    assert saw_excluded


def test_constructed_marks_enforced():
    # @criterion C6
    from cases.split import build_split

    res = build_split(synth_pools())
    for c in res["dev"] + res["test"]:
        assert c["message"]["constructed"] is True
        assert c["facts"]["cancelled"]["constructed"] is False
        for name, f in c["facts"].items():
            if name not in builder.BTS_FACTS:
                assert f["constructed"] is True
    bad = res["dev"][0]
    bad = {**bad, "facts": {**bad["facts"], "purchase_date": {"value": "2024-01-01"}}}
    with pytest.raises(ValueError, match="not marked constructed"):
        validate_case(bad)
    bad2 = {**res["dev"][0], "message": {"text": "x"}}
    with pytest.raises(ValueError):
        validate_case(bad2)


def _row(day):
    return {
        "carrier": "DL",
        "flight_number": "9",
        "date": day,
        "origin": "ATL",
        "destination": "JFK",
        "scheduled_departure": "0800",
        "actual_departure": "0800",
        "scheduled_arrival": "1000",
        "actual_arrival": "1000",
        "cancelled": "0",
        "diverted": "0",
        "cancellation_code": "",
    }


def test_excluded_date_is_left_out_and_listed():
    # @criterion C6
    from cases.split import build_split

    r = build_case("x", "renumbered", _row("2026-07-02"), 0, "dev")
    assert isinstance(r, Exclusion) and "2026-07-01" in r.reason
    assert not isinstance(
        build_case("x", "renumbered", _row("2026-07-07"), 0, "dev"), Exclusion
    )
    assert not isinstance(
        build_case("x", "delay_below", _row("2026-07-02"), 0, "dev"), Exclusion
    )

    pools = {
        t: {cm: list(v) for cm, v in by.items()} for t, by in synth_pools().items()
    }
    for cm, lst in pools["renumbered"].items():
        if cm.endswith("2026-07"):
            lst.insert(0, (_row("2026-07-03") | {"carrier": cm[:2]}, 0))
    res = build_split(pools)
    assert res["excluded"]
    listed = {e["bts_flight"]["date"] for e in res["excluded"]}
    assert "2026-07-03" in listed
    assert all("2026-07-01" <= d <= "2026-07-06" for d in listed)
    assert all(e["reason"] and e["type"] == "renumbered" for e in res["excluded"])
    ids = {
        c["bts_flight"]["date"]
        for c in res["dev"] + res["test"]
        if c["type"] == "renumbered"
    }
    assert not ids & listed


def test_clean_messages_agree_with_the_flight():
    # @criterion C6
    from cases.split import build_split

    res = build_split(synth_pools())
    for c in res["dev"] + res["test"]:
        if c["type"] == "adversarial":
            continue
        text = c["message"]["text"]
        cancelled = c["facts"]["cancelled"]["value"]
        d = c["facts"].get("arrival_delay_min", {}).get("value")
        if c["type"] in ("out_of_scope", "missing_fact"):
            continue
        if cancelled:
            assert "cancelled" in text and "late" not in text, text
        else:
            assert "cancelled" not in text, text
            if d < 15:
                assert (
                    "late" not in text.replace("arrived late", "LATE")
                    or c["type"] == "policies_differ"
                )
                assert "very late" not in text and "minutes late" not in text, text
            if d < 150:
                assert "very late" not in text, text
            if "minutes late" in text:
                assert f"{d} minutes late" in text
