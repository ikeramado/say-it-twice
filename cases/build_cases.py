"""Build cases from a clean BTS month: a real flight plus constructed facts and message.

A case names its BTS flight (`bts_flight`); everything about the passenger and the message is
constructed and marked so. Sampling is seeded, so the same month gives the same cases.
"""

import csv
import random
from pathlib import Path

N_CASES = 6
SEED = 20261118


def read_flights(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _type(row):
    return "cancelled" if row["cancelled"] == "1" else "delayed"


def build_case(i, row):
    code = f"{row['carrier']}{row['flight_number']}"
    ctype = _type(row)
    what = "was cancelled" if ctype == "cancelled" else "was badly delayed"
    return {
        "case_id": f"case-{i:03d}",
        "carrier": row["carrier"],
        "flight_number": row["flight_number"],
        "flight_date": row["date"],
        "origin": row["origin"],
        "type": ctype,
        "bts_flight": {
            k: row[k] for k in ("carrier", "flight_number", "date", "origin")
        },
        "facts": {
            "cancelled": {"value": row["cancelled"] == "1", "constructed": False},
            "passenger_name": {"value": f"Passenger {i:03d}", "constructed": True},
            "ticket_paid_usd": {"value": 100 + 25 * (i % 8), "constructed": True},
        },
        "message": {
            "text": f"My flight {code} on {row['date']} {what}. I want my money back.",
            "constructed": True,
        },
    }


def build_cases(flights_csv, n=N_CASES, seed=SEED):
    rows = read_flights(Path(flights_csv))
    rows.sort(
        key=lambda r: (
            r["carrier"],
            r["flight_number"].zfill(6),
            r["date"],
            r["origin"],
        )
    )
    picked = random.Random(seed).sample(rows, n)
    return [build_case(i, r) for i, r in enumerate(picked)]
