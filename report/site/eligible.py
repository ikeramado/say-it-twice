"""The count of eligible flights and passengers as an upper bound, for screen 1 (T53, ADR-0006).

Descriptive, outside the registered study. Domestic flights of Delta and American, from the
clean BTS data, that were cancelled or arrived 3 hours or more late on or after 2024-10-28
(rule version v2, clause v2-260.2-delay). Passengers: an upper bound from T-100 segment data.
"""

import csv
from collections import defaultdict
from pathlib import Path

from report.confirm import esc

CARRIERS = ("DL", "AA")
FROM_DAY = "2024-10-28"
LATE_MINUTES = 180


def eligible(row) -> bool:
    """Cancelled, or a recorded arrival 180 minutes or more late. A diverted flight counts
    only through the second test: v2-260.2-delay speaks of a consumer scheduled "to arrive at
    the destination airport three hours or more" later, and BTS leaves the arrival delay of a
    diverted flight empty unless it reached a destination."""
    if row["cancelled"] == "1":
        return True
    delay = row["arrival_delay"]
    return delay != "" and int(delay) >= LATE_MINUTES


def read_flights(flights_dir: Path) -> dict:
    """{(carrier, month, origin, destination): eligible flights} from the clean month files."""
    cells: dict[tuple, int] = defaultdict(int)
    for path in sorted(Path(flights_dir).glob("*.csv")):
        if path.stem < FROM_DAY[:7]:
            continue
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if r["carrier"] in CARRIERS and r["date"] >= FROM_DAY and eligible(r):
                    cells[
                        (r["carrier"], r["date"][:7], r["origin"], r["destination"])
                    ] += 1
    return cells


def read_t100(t100_dir) -> dict:
    """{(carrier, month, origin, destination): (passengers, departures)}."""
    out = {}
    if not t100_dir or not Path(t100_dir).is_dir():
        return out
    for path in sorted(Path(t100_dir).glob("*.csv")):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if r["carrier"] in CARRIERS:
                    month = f"{int(r['year']):04d}-{int(r['month']):02d}"
                    key = (r["carrier"], month, r["origin"], r["destination"])
                    out[key] = (int(r["passengers"]), int(r["departures"]))
    return out


def build_eligible(flights_dir, t100_dir=None) -> dict | None:
    """None when the clean data holds no month in the period. Otherwise the counts by carrier
    and month, the period, and `passengers` (None without T-100)."""
    flights_dir = Path(flights_dir)
    months = sorted(p.stem for p in flights_dir.glob("*.csv") if p.stem >= FROM_DAY[:7])
    if not months:
        return None
    cells = read_flights(flights_dir)
    by = {(c, m): 0 for c in CARRIERS for m in months}
    for (c, m, _o, _d), n in cells.items():
        by[(c, m)] += n
    t100 = read_t100(t100_dir)
    out = {
        "from": FROM_DAY,
        "to_month": months[-1],
        "by": by,
        "flights": sum(by.values()),
        "passengers": None,
        "no_t100_flights": 0,
    }
    if t100:
        total = 0.0
        missing = 0
        for key, n in cells.items():
            pax, dep = t100.get(key, (0, 0))
            if dep <= 0:
                missing += n
                continue
            # n flights of the cell take pax/dep each; never more than the cell's passengers
            total += min(n * pax / dep, pax)
        out["passengers"] = int(total)
        out["no_t100_flights"] = missing
    return out


NAMES = {"DL": "Delta", "AA": "American"}
FLIGHT_COUNT_ONLY = "flight count only"


def screen_line(e) -> str:
    """The HTML under the screen-1 table: the count, its period, the label and the method."""

    if e is None:
        return ""
    pax = (
        f" Up to {e['passengers']:,} passengers (an upper bound, not a count)."
        if e["passengers"] is not None
        else f" Passengers: {FLIGHT_COUNT_ONLY}, because BTS T-100 data was not "
        "ingested for this build."
    )
    rows = "".join(
        f"<tr><td>{esc(m)}</td>"
        + "".join(f"<td>{e['by'][(c, m)]:,}</td>" for c in CARRIERS)
        + "</tr>"
        for m in sorted({m for _c, m in e["by"]})
    )
    head = "".join(f"<th>{NAMES[c]}</th>" for c in CARRIERS)
    method = (
        "<p>Flights: the clean BTS on-time data, Delta (DL) and American (AA), every flight "
        f"dated {esc(e['from'])} (the v2 compliance date) or later that was cancelled, or "
        "whose recorded arrival was 180 minutes or more after the scheduled one (the "
        "three-hour domestic threshold of v2, clause v2-260.2-delay). A diverted flight "
        "counts only through its recorded arrival delay, which BTS leaves empty unless the "
        "flight reached a destination. The threshold is the same in v3 and v4.</p>"
        "<p>Passengers: BTS T-100 segment data, domestic rows. Each eligible flight takes "
        "its carrier-route-month's PASSENGERS divided by its DEPARTURES_PERFORMED; the "
        "figure is the sum over the eligible flights, with a carrier-route-month's share "
        "capped at its own PASSENGERS. A flight whose carrier-route-month T-100 lacks adds "
        f"nothing: {e['no_t100_flights']:,} flights here. Passengers who changed plans or "
        "did not ask for a refund are not removed, and a delayed passenger is owed the refund "
        "only if they did not fly the delayed flight (49 U.S.C. 42305(a); ADR-0008), which "
        "the data cannot tell, so it is an upper bound.</p>"
        f"<table><tr><th>Month</th>{head}</tr>{rows}</table>"
    )
    return (
        f'<p id="eligible"><strong>Descriptive, not part of the registered study.</strong> '
        f"From {esc(e['from'])} to the end of {esc(e['to_month'])}, "
        f"{e['flights']:,} domestic flights of Delta and American were cancelled or arrived "
        f"3 hours or more late.{pax} "
        f'<a href="#eligible-method">Method</a></p>'
        f'<details id="eligible-method"><summary>How this is counted</summary>{method}'
        "</details>"
    )
