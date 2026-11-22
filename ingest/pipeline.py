"""Ingest one BTS month through Write-Audit-Publish (C13)."""

import csv
import datetime
import hashlib
import io
import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)

# BTS column -> clean column
COLUMNS = {
    "Reporting_Airline": "carrier",
    "Flight_Number_Reporting_Airline": "flight_number",
    "FlightDate": "date",
    "Origin": "origin",
    "Dest": "destination",
    "CRSDepTime": "scheduled_departure",
    "DepTime": "actual_departure",
    "CRSArrTime": "scheduled_arrival",
    "ArrTime": "actual_arrival",
    "Cancelled": "cancelled",
    "Diverted": "diverted",
    "CancellationCode": "cancellation_code",
    "DepDelay": "departure_delay",
    "ArrDelay": "arrival_delay",
}
DELAYS = ("departure_delay", "arrival_delay")
KEY = ("carrier", "flight_number", "date", "origin")


def url_for(month: str) -> str:
    year, mon = month.split("-")
    return URL.format(year=year, month=int(mon))


def download(month: str, raw_dir: Path) -> Path:
    """Cache the monthly zip in raw_dir with its URL and download date; reuse it if present."""
    zip_path = raw_dir / "bts.zip"
    if zip_path.exists():
        return zip_path
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = url_for(month)
    tmp = zip_path.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=300) as resp, open(tmp, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    os.replace(tmp, zip_path)
    meta = {"url": url, "downloaded": datetime.date.today().isoformat()}
    (raw_dir / "source.json").write_text(json.dumps(meta) + "\n")
    return zip_path


def read_raw(zip_path: Path) -> tuple[list[str], list[dict]]:
    with zipfile.ZipFile(zip_path) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        text = io.TextIOWrapper(zf.open(name), encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text)
        return list(reader.fieldnames or []), list(reader)


def to_clean(row: dict) -> dict:
    out = {new: (row.get(old) or "").strip() for old, new in COLUMNS.items()}
    for flag in ("cancelled", "diverted"):
        out[flag] = str(int(float(out[flag] or 0)))
    for t in (
        "scheduled_departure",
        "actual_departure",
        "scheduled_arrival",
        "actual_arrival",
    ):
        out[t] = out[t].split(".")[0].zfill(4) if out[t] else ""
    for d in DELAYS:
        # BTS writes "15.00"; keep whole minutes, a non-number raises and quarantines
        out[d] = str(int(float(out[d]))) if out[d] else ""
    return out


def dedup(rows: list[dict]) -> list[dict]:
    seen, kept = set(), []
    for r in rows:
        k = tuple(r[c] for c in KEY)
        if k not in seen:
            seen.add(k)
            kept.append(r)
    return kept


def audit(header: list[str], raw_rows: int, clean: list[dict]) -> list[str]:
    """Return the failures; empty means the month may be published."""
    fails = []
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        fails.append(f"missing required columns: {missing}")
    keys = [tuple(r[c] for c in KEY) for r in clean]
    dup_left = len(keys) - len(set(keys))
    if dup_left:
        fails.append(f"{dup_left} duplicate keys left after dedup")
    return fails


def reconcile(raw_rows: int, dups_removed: int, clean_rows: int) -> list[str]:
    if raw_rows - dups_removed != clean_rows:
        return [
            f"row count does not reconcile: raw {raw_rows} - duplicates {dups_removed} != clean {clean_rows}"
        ]
    return []


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS.values()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def ingest(
    month: str, data_dir: Path, zip_path: Path | None = None
) -> tuple[bool, int, list[str]]:
    """Write (a temp table), audit, publish or quarantine. Returns (published, flights, failures)."""
    zip_path = zip_path or download(month, data_dir / "raw" / month)
    header, raw = read_raw(zip_path)
    failures = audit(
        header, len(raw), []
    )  # header check first: to_clean needs the columns
    if any(c not in header for c in COLUMNS):
        clean, dups = [], 0
    else:
        try:
            mapped = [to_clean(r) for r in raw]
        except (ValueError, OverflowError) as e:
            write_csv(data_dir / "quarantine" / f"{month}.csv", [])
            reason = f"non-numeric value in a delay or flag column: {e}"
            (data_dir / "quarantine" / f"{month}.reason.txt").write_text(reason + "\n")
            return False, 0, [reason]
        clean = dedup(mapped)
        dups = len(mapped) - len(mapped_unique(mapped))
        failures = audit(header, len(raw), clean) + reconcile(
            len(raw), dups, len(clean)
        )
    clean.sort(
        key=lambda r: (
            r["carrier"],
            r["flight_number"].zfill(6),
            r["date"],
            r["origin"],
        )
    )
    if failures:
        write_csv(data_dir / "quarantine" / f"{month}.csv", clean)
        (data_dir / "quarantine" / f"{month}.reason.txt").write_text(
            "\n".join(failures) + "\n"
        )
        return False, len(clean), failures
    write_csv(data_dir / "clean" / "flights" / f"{month}.csv", clean)
    return True, len(clean), []


def mapped_unique(rows: list[dict]) -> list[dict]:
    """Independent count of distinct keys, so the reconcile check does not reuse dedup."""
    return list({tuple(r[c] for c in KEY): r for r in rows}.values())


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m ingest.pipeline YYYY-MM", file=sys.stderr)
        return 2
    published, n, failures = ingest(argv[1], Path("data"))
    if not published:
        print("quarantined: " + "; ".join(failures), file=sys.stderr)
        return 1
    print(f"flights={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
