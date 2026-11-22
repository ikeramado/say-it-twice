"""Screen 4 of the site: the rule versions timeline and the date toggle (T48)."""

import csv
import os
import re
from datetime import date
from pathlib import Path

import pytest

from agents.system import engine
from report.site import ROOT, build
from report.site.timeline import CARRIER, EXAMPLES, build_timeline
from rules.lookup import policy_for, rule_for, rule_versions

FIX = Path(__file__).parent / "fixtures" / "site"
BTS = FIX / "bts"
CONFIG = ROOT / "config" / "site.yaml"


def build_html(tmp_path, flights_dir=BTS):
    build(tmp_path / "site", FIX / "report.json", CONFIG, flights_dir=flights_dir)
    return (tmp_path / "site" / "versions.html").read_text()


def section(html):
    return html.split('<section id="s4"')[1].split("</section>")[0]


def example(html, label):
    return section(html).split(f'aria-label="{label}"')[1].split('<div class="tlx"')[0]


def panel(ex_html, date):
    return ex_html.split(f"<h4>Date {date}")[1].split("</div>")[0]


@pytest.fixture(scope="module")
def html(tmp_path_factory):
    return build_html(tmp_path_factory.mktemp("tl"))


def test_every_version_is_on_the_timeline_with_date_and_source(html):
    s = section(html)
    versions = rule_versions()
    assert [v.id for v in versions] == ["v0", "v1", "v2", "v3", "v4"]
    for v in versions:
        item = s.split(f"<strong>{v.id}</strong>")[1].split("</li>")[0]
        assert f"effective {v.first_day} to " in item
        assert f"to {v.last_day or 'today, no end date'}" in item
        for src in v.source_files:
            assert Path(src).name in item


def test_the_july_flights_sit_on_their_version(html):
    v1 = section(html).split("<strong>v1</strong>")[1].split("</li>")[0]
    for label in (
        "DL 31 ATL, 2024-07-19",
        "DL 32 DFW, 2024-07-19",
        "DL 300 ATL, 2024-07-20",
    ):
        assert label in v1
    v0 = section(html).split("<strong>v0</strong>")[1].split("</li>")[0]
    assert "Delta flights" not in v0


# @criterion C10
def test_moving_the_date_changes_version_and_decision_for_the_fixture_flight(html):
    ex = example(html, "DL 300 ATL, 2024-07-20")
    expected = {
        "2024-03-01": ("v0", "escalate"),
        "2024-07-20": ("v1", "escalate"),
        "2025-03-01": ("v2", "refund"),
        "2026-01-15": ("v3", "no refund"),
        "2026-08-01": ("v4", "no refund"),
    }
    for day, (ver, dec) in expected.items():
        p = panel(ex, day)
        assert f"Version in force: <strong>{ver}</strong>" in p
        assert f"Engine decision: <strong>{dec}</strong>" in p
    assert len({v for v, _ in expected.values()}) == 5
    assert len({d for _, d in expected.values()}) == 3


def test_the_decision_on_the_page_is_the_engines_for_that_version(tmp_path):
    flights = build_timeline(BTS)
    assert len(flights) == len(EXAMPLES)
    for ex, spec in zip(flights, EXAMPLES, strict=True):
        facts = {k: v for k, v, _ in ex["listed"]}
        pol = policy_for(CARRIER, date.fromisoformat(facts["purchase_date"]))
        for p in ex["positions"]:
            rule = rule_for(date.fromisoformat(p["date"]), spec["renumbered"])
            assert p["rule_version"] == rule.id
            assert p["decision"] == engine.decide(facts, rule, pol)["decision"]
            assert p["policy_version"] == "DL-2024-03-12"


def test_real_facts_come_from_the_bts_row_and_control_flights_do_not_change(html):
    cancelled = example(html, "DL 31 ATL, 2024-07-19")
    assert "cancelled: yes (from BTS)" in cancelled
    late = example(html, "DL 32 DFW, 2024-07-19")
    assert "arrival_delay_min: 193 (from BTS)" in late
    for ex in (cancelled, late):
        decisions = set(re.findall(r"Engine decision: <strong>([^<]*)</strong>", ex))
        assert decisions == {"refund"}


def test_constructed_facts_are_labeled(html):
    ex = example(html, "DL 300 ATL, 2024-07-20")
    for line in (
        "purchase_date: 2024-06-20 (constructed for this page)",
        "alternative_accepted: no (constructed for this page)",
        "renumbered: yes (constructed for this page)",
        "significant_change: no (constructed for this page)",
        "arrival_delay_min: 90 (from BTS)",
        "cancelled: no (from BTS)",
    ):
        assert line in ex
    assert "30 days before its flight" in section(html)


def test_a_date_before_the_study_window_is_excluded_and_escalates():
    rule = rule_for(date(2023, 12, 31), False)
    assert rule.reason.startswith("flight date 2023-12-31 is before")
    res = engine.decide(
        {"cancelled": True}, rule, policy_for(CARRIER, date(2024, 6, 20))
    )
    assert (res["decision"], res["clause"]) == ("escalate", "excluded_rule")


def test_without_the_bts_file_the_timeline_stays_and_says_the_flights_are_missing(
    tmp_path,
):
    empty = tmp_path / "none"
    empty.mkdir()
    s = section(build_html(tmp_path, empty))
    assert "<strong>v4</strong>" in s
    assert "The July 2024 flights are not in this build" in s
    assert "tlx" not in s.replace("<style>", "").split("</style>")[-1]


def test_a_flight_row_missing_from_the_file_is_left_out(tmp_path):
    d = tmp_path / "part"
    d.mkdir()
    rows = list(csv.reader((BTS / "2024-07.csv").open()))
    with (d / "2024-07.csv").open("w", newline="") as f:
        csv.writer(f).writerows([r for r in rows if r[1] != "300"])
    labels = [e["label"] for e in build_timeline(d)]
    assert labels == ["DL 31 ATL, 2024-07-19", "DL 32 DFW, 2024-07-19"]


def test_no_script_and_one_radio_group_per_example(html):
    s = section(html)
    assert "<script" not in s
    assert len(re.findall(r'type="radio"', s)) == 3 * 5
    assert len(set(re.findall(r'name="(tl-\d)"', s))) == 3


def test_the_examples_are_real_rows_of_the_bts_file():
    real = (
        Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT)
        / "data/clean/flights/2024-07.csv"
    )
    if not real.exists():
        pytest.skip(f"{real} is not here (BTS data is git-ignored)")
    with real.open(newline="") as f:
        rows = {
            (r["carrier"], r["flight_number"], r["date"], r["origin"]): r
            for r in csv.DictReader(f)
        }
    expected = {
        "31": ("1", ""),  # cancelled
        "32": ("0", "193"),
        "300": ("0", "90"),
    }
    for ex in EXAMPLES:
        row = rows[(CARRIER, ex["number"], ex["date"], ex["origin"])]
        assert (row["cancelled"], row["arrival_delay"]) == expected[ex["number"]]
    built = {
        e["label"]: {k: v for k, v, _ in e["listed"]}
        for e in build_timeline(real.parent)
    }
    assert len(built) == len(EXAMPLES)
    assert built["DL 31 ATL, 2024-07-19"]["cancelled"] is True
    assert built["DL 32 DFW, 2024-07-19"]["arrival_delay_min"] == 193
    assert built["DL 300 ATL, 2024-07-20"]["arrival_delay_min"] == 90
