"""Ingest one year of BTS T-100 segment data (T53, ADR-0006): domestic passengers and departures.

Source: the "T-100 Segment (All Carriers)" table of transtats.bts.gov (it has no PREZIP file, so
the download form is posted once per year). The clean file keeps the domestic rows (both
countries US), summed over aircraft types, per carrier, route and month.
"""

import csv
import datetime
import hashlib
import html
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path

URL = (
    "https://www.transtats.bts.gov/DL_SelectFields.aspx"
    "?gnoyr_VQ=FMG&QO_fu146_anzr=Nv4%20Pn44vr45"
)
TABLE = "T-100 Segment (All Carriers)"
FIELDS = (
    "YEAR",
    "MONTH",
    "UNIQUE_CARRIER",
    "ORIGIN",
    "DEST",
    "PASSENGERS",
    "DEPARTURES_PERFORMED",
    "ORIGIN_COUNTRY",  # only to keep the domestic rows
    "DEST_COUNTRY",
)
CLEAN = (
    "carrier",
    "year",
    "month",
    "origin",
    "destination",
    "passengers",
    "departures",
)


def download(year: int, raw_dir: Path) -> Path:
    """Post the form for one year, cache the zip in raw_dir with its URL, date and hash."""
    zip_path = raw_dir / f"{year}.zip"
    if zip_path.exists():
        return zip_path
    raw_dir.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )
    page = opener.open(URL, timeout=120).read().decode("utf-8", "ignore")
    form = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        form[name] = html.unescape(
            re.search(rf'name="{name}"[^>]*value="([^"]*)"', page).group(1)
        )
    form.update(
        cboGeography="All",
        cboYear=str(year),
        cboPeriod="All",
        chkDownloadZip="on",
        btnDownload="Download",
    )
    form.update({f: "on" for f in FIELDS})
    req = urllib.request.Request(URL, urllib.parse.urlencode(form).encode())
    body = opener.open(req, timeout=600).read()
    if body[:2] != b"PK":
        raise RuntimeError(f"T-100 {year}: BTS did not answer with a zip")
    tmp = zip_path.with_suffix(".part")
    tmp.write_bytes(body)
    os.replace(tmp, zip_path)
    meta = {
        "url": URL,
        "table": TABLE,
        "year": year,
        "downloaded": datetime.date.today().isoformat(),
        "zip_sha256": hashlib.sha256(body).hexdigest(),
    }
    (raw_dir / f"{year}.json").write_text(json.dumps(meta, indent=1) + "\n")
    return zip_path


def read_raw(zip_path: Path) -> tuple[list[str], list[dict]]:
    with zipfile.ZipFile(zip_path) as zf:
        name = next(
            n
            for n in zf.namelist()
            if n.lower().endswith(".csv") and "documentation" not in n.lower()
        )
        text = io.TextIOWrapper(zf.open(name), encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text)
        return list(reader.fieldnames or []), list(reader)


def to_clean(raw: list[dict]) -> list[dict]:
    """Domestic rows summed per carrier, route and month; a bad number raises ValueError."""
    cells: dict[tuple, list[int]] = {}
    for r in raw:
        if r["ORIGIN_COUNTRY"] != "US" or r["DEST_COUNTRY"] != "US":
            continue
        key = (
            r["UNIQUE_CARRIER"].strip(),
            int(r["YEAR"]),
            int(r["MONTH"]),
            r["ORIGIN"].strip(),
            r["DEST"].strip(),
        )
        pax, dep = (
            int(float(r["PASSENGERS"] or 0)),
            int(float(r["DEPARTURES_PERFORMED"] or 0)),
        )
        if pax < 0 or dep < 0:
            raise ValueError(f"negative value for {key}")
        acc = cells.setdefault(key, [0, 0])
        acc[0] += pax
        acc[1] += dep
    return [
        dict(zip(CLEAN, (c, y, m, o, d, p, n), strict=True))
        for (c, y, m, o, d), (p, n) in sorted(cells.items())
    ]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CLEAN), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ingest(
    year: int, data_dir: Path, zip_path: Path | None = None
) -> tuple[bool, int, list[str]]:
    """Returns (published, rows, failures). Same zip, same clean file, same hash."""
    raw_dir = data_dir / "raw" / "t100"
    zip_path = zip_path or download(year, raw_dir)
    header, raw = read_raw(zip_path)
    missing = [f for f in FIELDS if f not in header]
    if missing:
        return False, 0, [f"missing required columns: {missing}"]
    try:
        rows = to_clean(raw)
    except (ValueError, KeyError) as e:
        return False, 0, [f"bad value: {e}"]
    if not rows:
        return False, 0, [f"no domestic rows for {year}"]
    if {r["year"] for r in rows} != {year}:
        return False, 0, [f"rows outside {year}"]
    out = data_dir / "clean" / "t100" / f"{year}.csv"
    write_csv(out, rows)
    meta_path = raw_dir / f"{year}.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        meta["clean_sha256"] = file_hash(out)
        meta_path.write_text(json.dumps(meta, indent=1) + "\n")
    return True, len(rows), []


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].isdigit():
        print("usage: python -m ingest.t100 YYYY", file=sys.stderr)
        return 2
    published, n, failures = ingest(int(argv[1]), Path("data"))
    if not published:
        print("not published: " + "; ".join(failures), file=sys.stderr)
        return 1
    print(f"rows={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
