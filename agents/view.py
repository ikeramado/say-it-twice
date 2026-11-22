"""The agents' view of a case: the only place an agent gets a case from.

Keeps what a customer-facing agent would see and drops what would leak the answer: the case
id becomes an opaque id, and `type`, `meta`, `clean_case_id`, `attack`, `contradicts_facts`,
`bts_flight` and every `constructed` flag are left out (the view is built from a list of kept
keys, so a field added to the case later stays out too).
"""

import hashlib

SALT = "say-it-twice-agents"
KEYS = ("id", "carrier", "flight_number", "flight_date", "origin", "facts", "message")


def opaque_id(case_id: str) -> str:
    """SHA-256 of case id + SALT, first 10 hex: stable, and says nothing of the case type.

    Reimplemented apart from labeling's (another salt): agents never import labeling."""
    return hashlib.sha256((case_id + SALT).encode("utf-8")).hexdigest()[:10]


def _text(x):
    return None if x is None else str(x)


def view(case: dict) -> dict:
    """A flight field absent or null in the case (the DOT guidance case) is None."""
    msg = case["message"]
    return {
        "id": opaque_id(case["case_id"]),
        "carrier": case.get("carrier"),
        "flight_number": _text(case.get("flight_number")),
        "flight_date": _text(case.get("flight_date")),
        "origin": case.get("origin"),
        "facts": {name: f["value"] for name, f in case["facts"].items()},
        "message": msg["text"] if isinstance(msg, dict) else msg,
    }
