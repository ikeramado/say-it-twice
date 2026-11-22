"""The count of eligible flights and the screen-1 line (T53, ADR-0006, C10)."""

import re
from pathlib import Path

import pytest

from report.site import ROOT, build
from report.site.eligible import FLIGHT_COUNT_ONLY, build_eligible, eligible
from rules.lookup import rule_versions

FIX = Path(__file__).parent / "fixtures" / "eligible"
SITE_REPORT = Path(__file__).parent / "fixtures" / "site" / "report.json"
CONFIG = ROOT / "config" / "site.yaml"


def test_cancelled_179_180_and_the_day_before_give_two():
    # @criterion C10
    # basic/2024-10: cancelled 10-28, 180 min late, 179 min late, cancelled 10-27
    r = build_eligible(FIX / "basic" / "flights")
    assert r["by"][("DL", "2024-10")] == 2


def test_a_diverted_flight_is_counted_as_the_versions_text_says():
    # @criterion C10
    text = next(
        c.text
        for v in rule_versions()
        if v.id == "v2"
        for c in v.clauses
        if c.id == "v2-260.2-delay"
    )
    assert "arrive at the destination airport three hours or more" in text
    base = {"cancelled": "0", "diverted": "1"}
    # no recorded arrival delay: the consumer's arrival is not known to be 3 hours late
    assert eligible({**base, "arrival_delay": ""}) is False
    assert eligible({**base, "arrival_delay": "200"}) is True
    r = build_eligible(FIX / "basic" / "flights")
    assert r["by"][("DL", "2024-11")] == 1  # the diverted 200-minute flight only


def test_only_delta_and_american_and_only_from_the_compliance_date():
    r = build_eligible(FIX / "basic" / "flights")
    assert r["from"] == "2024-10-28"
    assert r["by"][("AA", "2024-11")] == 0
    assert r["flights"] == 3  # UA is not counted, nor the cancellation of 10-27
    assert r["to_month"] == "2024-11"


def test_no_month_in_the_period_gives_none(tmp_path):
    (tmp_path / "2024-09.csv").write_text("carrier\n")
    assert build_eligible(tmp_path) is None
    assert build_eligible(tmp_path / "missing") is None


def test_passengers_are_spread_by_departures_and_capped_per_route_month():
    r = build_eligible(FIX / "full" / "flights", FIX / "full" / "t100")
    assert r["by"] == {
        ("DL", "2024-10"): 2,
        ("AA", "2024-10"): 0,
        ("DL", "2024-11"): 1,
        ("AA", "2024-11"): 3,
    }
    assert r["flights"] == 6
    # DL JFK-ATL 2024-10: 2 flights x 1000/10 = 200; AA ORD-DFW 2024-11: 3 x 300/2 = 450,
    # capped at the cell's 300; DL SEA-PDX 2024-11 has no T-100 row: adds nothing
    assert r["passengers"] == 500
    assert r["no_t100_flights"] == 1


def test_without_t100_the_flight_count_stands_alone():
    r = build_eligible(FIX / "full" / "flights", FIX / "full" / "absent")
    assert r["passengers"] is None
    assert r["flights"] == 6


def test_a_route_month_with_no_departures_adds_nothing(tmp_path):
    t = tmp_path / "t100"
    t.mkdir()
    (t / "2024.csv").write_text(
        "carrier,year,month,origin,destination,passengers,departures\n"
        "DL,2024,10,JFK,ATL,900,0\n"
    )
    r = build_eligible(FIX / "full" / "flights", t)
    assert r["passengers"] == 0
    # no cell has departures: the two DL JFK-ATL flights, DL SEA-PDX and the three AA ORD-DFW
    assert r["no_t100_flights"] == 6
    assert r["flights"] == 6


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    out = {}
    for name in ("full", "basic"):
        d = tmp_path_factory.mktemp(name)
        build(d, SITE_REPORT, CONFIG, flights_dir=FIX / name / "flights")
        html = (d / "method.html").read_text()
        out[name] = html.split('<section id="eligible-section"')[1].split("</section>")[0]
    return out


def test_screen_one_shows_count_period_passengers_and_label(pages):
    # @criterion C10
    s = pages["full"]
    line = re.search(r'<p id="eligible">.*?</p>', s, re.DOTALL).group(0)
    assert "Descriptive, not part of the registered study" in line
    assert "From 2024-10-28 to the end of 2024-11" in line
    assert "6 domestic flights of Delta and American" in line
    assert "Up to 500 passengers" in line
    assert 'href="#eligible-method"' in line
    assert 'id="eligible-method"' in s


def test_the_method_gives_the_division_and_the_missing_count(pages):
    method = pages["full"].split('id="eligible-method"')[1]
    assert "PASSENGERS divided by its DEPARTURES_PERFORMED" in method
    assert "1 flights here" in method
    assert "<td>2024-11</td><td>1</td><td>3</td>" in method  # Delta 1, American 3


def test_without_t100_the_line_says_flight_count_only(pages):
    # @criterion C10
    line = re.search(r'<p id="eligible">.*?</p>', pages["basic"], re.DOTALL).group(0)
    assert FLIGHT_COUNT_ONLY in line
    assert "Up to" not in line
    assert "3 domestic flights" in line
    assert "Descriptive" in line


def test_real_data_count_matches_an_independent_count():
    # @criterion C10
    import csv
    import os

    root = Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT) / "data/clean"
    months = (
        sorted((root / "flights").glob("*.csv")) if (root / "flights").is_dir() else []
    )
    months = [m for m in months if m.stem >= "2024-10"]
    if not months:
        pytest.skip("no clean BTS months from 2024-10 in this checkout")
    n = 0
    for m in months:
        for r in csv.DictReader(m.read_text().splitlines()):
            late = r["arrival_delay"] != "" and float(r["arrival_delay"]) >= 180
            if r["carrier"] in ("DL", "AA") and r["date"] >= "2024-10-28":
                n += r["cancelled"] == "1" or late
    got = build_eligible(root / "flights", root / "t100")
    assert got["flights"] == n
    assert got["to_month"] == months[-1].stem
    if got["passengers"] is not None:
        assert 0 <= got["passengers"]


def test_the_method_says_a_delayed_passenger_is_owed_the_refund_only_if_they_did_not_fly(
    pages,
):
    # @criterion C10
    method = pages["full"].split('id="eligible-method"')[1]
    assert "did not fly" in method
    assert "so it is an upper bound" in method
