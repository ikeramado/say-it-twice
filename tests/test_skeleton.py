from pathlib import Path

import pytest

from cases.build_cases import build_cases
from ingest import pipeline
from llm import provider
from report import skeleton

FIXTURE = Path(__file__).parent / "fixtures" / "bts" / "2024-07.zip"
MONTH = "2024-07"


def clean_month(tmp_path):
    pipeline.ingest(MONTH, tmp_path, FIXTURE)
    return tmp_path / "clean" / "flights" / f"{MONTH}.csv"


def test_constructed_marks(tmp_path):
    # @criterion C1
    flights = clean_month(tmp_path)
    cases = build_cases(flights)
    assert len(cases) == 6
    assert cases == build_cases(flights)  # seeded
    keys = {
        (r["carrier"], r["flight_number"], r["date"], r["origin"])
        for r in pipeline.csv.DictReader(flights.open())
    }
    for c in cases:
        assert tuple(c["bts_flight"].values()) in keys
        assert c["message"]["constructed"] is True
        assert c["facts"]["passenger_name"]["constructed"] is True
        assert c["facts"]["ticket_paid_usd"]["constructed"] is True


def test_end_to_end_no_model_call(tmp_path, monkeypatch):
    # @criterion C1
    def boom(*a, **k):
        raise AssertionError("a real provider was called")

    monkeypatch.setattr(provider, "real_provider", boom)
    out, s = skeleton.skeleton(
        MONTH, data_dir=tmp_path / "data", runs_dir=tmp_path / "runs", zip_path=FIXTURE
    )
    page = out.read_text()
    assert "Consistency share" in page and "95%" in page
    assert 0 <= s["low"] <= s["share"] <= s["high"] <= 1
    assert f"{100 * s['share']:.1f}%" in page
    costs = (out.parent / "costs.jsonl").read_text().splitlines()
    assert len(costs) == 60
    with pytest.raises(AssertionError):
        provider.real_provider("x", "y", 1)
