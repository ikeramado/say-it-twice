import csv
import shutil
import zipfile
from pathlib import Path

import pytest

from ingest import pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "bts" / "2024-07.zip"
MONTH = "2024-07"


def run(tmp_path, zip_path=FIXTURE):
    return pipeline.ingest(MONTH, tmp_path, zip_path)


def test_idempotent(tmp_path):
    # @criterion C13
    ok, n, _ = run(tmp_path)
    assert ok and n == 24  # 25 raw rows, 1 duplicate
    f = tmp_path / "clean" / "flights" / f"{MONTH}.csv"
    first = pipeline.file_hash(f)
    run(tmp_path)
    assert pipeline.file_hash(f) == first
    rows = list(csv.DictReader(f.open()))
    assert sum(r["cancelled"] == "1" for r in rows) == 1


def test_reconcile(tmp_path, monkeypatch):
    # @criterion C13
    ok, n, _ = run(tmp_path)
    assert ok and 25 - 1 == n
    # a dedup that loses an extra row must not publish
    bad = tmp_path / "bad"
    monkeypatch.setattr(
        pipeline, "dedup", lambda rows: pipeline.mapped_unique(rows)[1:]
    )
    ok, _, failures = pipeline.ingest(MONTH, bad, FIXTURE)
    assert not ok
    assert any("reconcile" in f for f in failures)
    assert not (bad / "clean").exists()
    assert (bad / "quarantine" / f"{MONTH}.csv").exists()


def test_missing_column_quarantined(tmp_path):
    # @criterion C13
    z = tmp_path / "x.zip"
    with zipfile.ZipFile(FIXTURE) as src, zipfile.ZipFile(z, "w") as dst:
        text = src.read(src.namelist()[0]).decode().replace("Dest,", "Dst,", 1)
        dst.writestr("a.csv", text)
    ok, _, failures = pipeline.ingest(MONTH, tmp_path / "d", z)
    assert not ok and "missing" in failures[0]


def test_columns(tmp_path):
    # @criterion C13
    run(tmp_path)
    f = tmp_path / "clean" / "flights" / f"{MONTH}.csv"
    header = next(csv.reader(f.open()))
    assert header == [
        "carrier", "flight_number", "date", "origin", "destination",
        "scheduled_departure", "actual_departure", "scheduled_arrival", "actual_arrival",
        "cancelled", "diverted", "cancellation_code",
        "departure_delay", "arrival_delay",
    ]  # fmt: skip
    rows = list(csv.DictReader(f.open()))
    assert [r["carrier"] for r in rows] == sorted(r["carrier"] for r in rows)


def test_cached_download_not_refetched(tmp_path, monkeypatch):
    # @criterion C13
    raw = tmp_path / "raw" / MONTH
    raw.mkdir(parents=True)
    shutil.copy(FIXTURE, raw / "bts.zip")
    monkeypatch.setattr(pipeline.urllib.request, "urlopen", pytest.fail)
    assert pipeline.ingest(MONTH, tmp_path)[0]


def _zip_with(tmp_path, extra_lines):
    z = tmp_path / "d.zip"
    with zipfile.ZipFile(FIXTURE) as src, zipfile.ZipFile(z, "w") as dst:
        text = src.read(src.namelist()[0]).decode()
        dst.writestr("a.csv", text + "\n".join(extra_lines) + "\n")
    return z


def test_official_delay(tmp_path):
    # @criterion C13
    z = _zip_with(
        tmp_path,
        [
            "DL,901,2024-07-10,ATL,SEA,0600,0705.0,0830,0935.0,0.0,0.0,,2024,1500.00,1500.00",
            "DL,902,2024-07-10,ATL,SEA,0600,0705.0,0830,0935.0,0.0,0.0,,2024,1320.00,1320.00",
            "DL,903,2024-07-10,ATL,SEA,0600,0605.0,0830,0815.0,0.0,0.0,,2024,-5.00,-15.00",
        ],
    )
    ok, _, _ = pipeline.ingest(MONTH, tmp_path / "d", z)
    assert ok
    f = tmp_path / "d" / "clean" / "flights" / f"{MONTH}.csv"
    got = {r["flight_number"]: r for r in csv.DictReader(f.open())}
    assert [got[k]["arrival_delay"] for k in ("901", "902", "903")] == [
        "1500", "1320", "-15",
    ]  # fmt: skip
    cancelled = next(r for r in got.values() if r["cancelled"] == "1")
    assert cancelled["arrival_delay"] == "" and cancelled["departure_delay"] == ""


def test_official_delay_non_numeric_quarantined(tmp_path):
    # @criterion C13
    z = _zip_with(
        tmp_path,
        ["DL,904,2024-07-10,ATL,SEA,0600,0605.0,0830,0815.0,0.0,0.0,,2024,x,y"],
    )
    ok, _, failures = pipeline.ingest(MONTH, tmp_path / "d", z)
    assert not ok and any("delay" in f for f in failures)
    assert not (tmp_path / "d" / "clean").exists()


def test_official_delay_infinite_quarantined(tmp_path):
    # @criterion C13
    z = _zip_with(
        tmp_path,
        ["DL,905,2024-07-10,ATL,SEA,0600,0605.0,0830,0815.0,0.0,0.0,,2024,inf,Infinity"],
    )
    ok, _, failures = pipeline.ingest(MONTH, tmp_path / "d", z)
    assert not ok and any("delay" in f for f in failures)
    assert not (tmp_path / "d" / "clean").exists()
