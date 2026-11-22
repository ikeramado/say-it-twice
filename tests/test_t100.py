"""The T-100 ingest (T53, ADR-0006): domestic rows, sums, same hash on a re-ingest."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from ingest import t100
from report.site.eligible import build_eligible

HEAD = ",".join(t100.FIELDS)
FIX = Path(__file__).parent / "fixtures" / "eligible"


def make_zip(path, rows, head=HEAD):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = head + "\n" + "\n".join(rows) + "\n"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Documentation.csv", "SYS_FIELD_NAME,FIELD_DESC\nYEAR,Year\n")
        zf.writestr("T_T100_SEGMENT_ALL_CARRIER.csv", body)
    return path


# YEAR,MONTH,UNIQUE_CARRIER,ORIGIN,DEST,PASSENGERS,DEPARTURES_PERFORMED,ORIGIN_COUNTRY,DEST_COUNTRY
ROWS = [
    "2024,10,DL,JFK,ATL,600.00,6.00,US,US",
    "2024,10,DL,JFK,ATL,400.00,4.00,US,US",  # a second aircraft type, summed
    "2024,10,DL,JFK,LHR,900.00,5.00,US,GB",  # international, dropped
    "2024,11,AA,ORD,DFW,300.00,2.00,US,US",
]


def test_clean_rows_are_domestic_and_summed_per_carrier_route_month(tmp_path):
    z = make_zip(tmp_path / "in" / "2024.zip", ROWS)
    ok, n, fails = t100.ingest(2024, tmp_path / "data", z)
    assert (ok, n, fails) == (True, 2, [])
    lines = (tmp_path / "data/clean/t100/2024.csv").read_text().splitlines()
    assert lines == [
        "carrier,year,month,origin,destination,passengers,departures",
        "AA,2024,11,ORD,DFW,300,2",
        "DL,2024,10,JFK,ATL,1000,10",
    ]


def test_a_re_ingest_gives_the_same_file_hash(tmp_path):
    z = make_zip(tmp_path / "in" / "2024.zip", ROWS)
    t100.ingest(2024, tmp_path / "data", z)
    out = tmp_path / "data/clean/t100/2024.csv"
    first = t100.file_hash(out)
    out.unlink()
    t100.ingest(2024, tmp_path / "data", z)
    assert t100.file_hash(out) == first


def test_the_provenance_keeps_url_date_and_both_hashes(tmp_path, monkeypatch):
    make_zip(tmp_path / "src.zip", ROWS)
    body = (tmp_path / "src.zip").read_bytes()

    class Resp(io.BytesIO):
        pass

    class Opener:
        def open(self, req, timeout=0):
            if isinstance(req, str):
                return Resp(
                    b'<input name="__VIEWSTATE" value="a&amp;b" />'
                    b'<input name="__VIEWSTATEGENERATOR" value="g" />'
                    b'<input name="__EVENTVALIDATION" value="e" />'
                )
            assert b"cboYear=2024" in req.data
            assert b"PASSENGERS=on" in req.data
            return Resp(body)

    monkeypatch.setattr(t100.urllib.request, "build_opener", lambda *a: Opener())
    ok, _n, fails = t100.ingest(2024, tmp_path / "data")
    assert (ok, fails) == (True, [])
    meta = json.loads((tmp_path / "data/raw/t100/2024.json").read_text())
    assert meta["url"] == t100.URL
    assert meta["zip_sha256"] and meta["downloaded"]
    assert meta["clean_sha256"] == t100.file_hash(tmp_path / "data/clean/t100/2024.csv")


def test_a_download_that_is_not_a_zip_raises(tmp_path, monkeypatch):
    class Opener:
        def open(self, req, timeout=0):
            return io.BytesIO(
                b'<input name="__VIEWSTATE" value="a" /><input name="__VIEWSTATEGENERATOR" value="g" />'
                b'<input name="__EVENTVALIDATION" value="e" />'
                if isinstance(req, str)
                else b"<html>error</html>"
            )

    monkeypatch.setattr(t100.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(RuntimeError, match="did not answer with a zip"):
        t100.download(2024, tmp_path)
    assert not (tmp_path / "2024.zip").exists()


@pytest.mark.parametrize(
    "rows, head, message",
    [
        (ROWS, HEAD.replace("PASSENGERS,", ""), "missing required columns"),
        (["2024,10,DL,JFK,ATL,-5,6,US,US"], HEAD, "negative"),
        (["2024,10,DL,JFK,ATL,many,6,US,US"], HEAD, "bad value"),
        (["2024,10,DL,JFK,LHR,9,5,US,GB"], HEAD, "no domestic rows"),
        (["2023,10,DL,JFK,ATL,9,5,US,US"], HEAD, "rows outside 2024"),
    ],
)
def test_a_bad_file_is_not_published(tmp_path, rows, head, message):
    z = make_zip(tmp_path / "in" / "2024.zip", rows, head)
    ok, n, fails = t100.ingest(2024, tmp_path / "data", z)
    assert (ok, n) == (False, 0)
    assert message in fails[0]
    assert not (tmp_path / "data/clean/t100/2024.csv").exists()


def test_the_bound_is_not_negative_and_not_above_the_cells_that_hold_eligible_flights():
    r = build_eligible(FIX / "full" / "flights", FIX / "full" / "t100")
    # cells holding eligible flights with a T-100 row: DL JFK-ATL 2024-10 (1000), AA ORD-DFW (300)
    assert 0 <= r["passengers"] <= 1000 + 300
