import json
import os
import re
from datetime import date
from pathlib import Path

import pytest
import yaml

from report.site import ROOT, build
from report.site.freshness import freshness_line

FIXTURES = Path(__file__).parent / "fixtures" / "freshness"
REPORT = Path(__file__).parent / "fixtures" / "site" / "report.json"
CONFIG = ROOT / "config" / "site.yaml"
CFG = yaml.safe_load(CONFIG.read_text())
MISSING = "Flight data freshness is not available in this build."
TODAY = date(2026, 11, 22)


def index(tmp_path, data_root, today=TODAY):
    build(tmp_path, REPORT, CONFIG, data_root=data_root, today=today)
    return (tmp_path / "index.html").read_text()


# @criterion C15
def test_the_index_carries_the_label_of_the_fixture(tmp_path):
    html = index(tmp_path, FIXTURES / "full")
    assert (
        '<footer class="col"><p class="freshness">Flight data through July 2026 (BTS), '
        "last loaded on 2026-11-18, 4 days before this build.</p></footer>"
    ) in html


# @criterion C15
def test_no_flight_data_gives_the_not_available_sentence(tmp_path):
    html = index(tmp_path, FIXTURES / "empty")
    assert f'<p class="freshness">{MISSING}</p>' in html


# @criterion C15
def test_one_day_is_singular():
    line = freshness_line(CFG, FIXTURES / "full", date(2026, 11, 19))
    assert line.endswith("1 day before this build.")


# @criterion C15
def test_every_unreadable_input_gives_the_sentence(tmp_path):
    flights = tmp_path / "data/clean/flights"
    flights.mkdir(parents=True)
    (flights / "2026-07.csv").touch()
    assert freshness_line(CFG, tmp_path, TODAY) == MISSING  # no source.json
    raw = tmp_path / "data/raw/2026-07"
    raw.mkdir(parents=True)
    (raw / "source.json").write_text("{not json")
    assert freshness_line(CFG, tmp_path, TODAY) == MISSING  # malformed
    (raw / "source.json").write_text(json.dumps({"downloaded": "2026-11-18"}))
    assert freshness_line(CFG, tmp_path, TODAY).startswith("Flight data through July 2026")
    (flights / "latest.csv").touch()
    assert freshness_line(CFG, tmp_path, TODAY) == MISSING  # not YYYY-MM


# @criterion C15
def test_real_freshness():
    root = Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT)
    months = sorted(p.stem for p in (root / "data/clean/flights").glob("*.csv"))
    if not months:
        pytest.skip("no real clean flights")
    loaded = max(
        json.loads(p.read_text())["downloaded"]
        for p in (root / "data/raw").glob("*/source.json")
    )
    line = freshness_line(CFG, root, TODAY)
    m = re.match(r"Flight data through (\w+ \d{4}) \(BTS\), last loaded on (\S+?),", line)
    assert m, line
    assert m[1] == f"{date.fromisoformat(months[-1] + '-01'):%B %Y}"
    assert m[2] == loaded
