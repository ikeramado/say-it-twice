"""The freshness label of the index (C15): the latest month of the clean flights, the date of
the last ingest and the days between that ingest and the build. Any missing or unreadable input
gives the not-available sentence of `config/site.yaml`; the build never fails on it."""

import json
import re
from datetime import date
from pathlib import Path

MONTH = re.compile(r"\d{4}-\d{2}")


def latest_month(data_root):
    """The latest `<YYYY-MM>` file name in data/clean/flights, a ValueError when there is none
    or one is not a month."""
    names = [p.stem for p in (Path(data_root) / "data/clean/flights").glob("*.csv")]
    if not names or not all(MONTH.fullmatch(n) for n in names):
        raise ValueError("no clean flights, or a file name that is not YYYY-MM")
    month = max(names)
    date.fromisoformat(month + "-01")
    return month


def last_ingest(data_root):
    """The latest `downloaded` date among data/raw/*/source.json, a ValueError when none."""
    days = [
        date.fromisoformat(json.loads(p.read_text())["downloaded"])
        for p in (Path(data_root) / "data/raw").glob("*/source.json")
    ]
    if not days:
        raise ValueError("no source.json")
    return max(days)


def freshness_line(cfg, data_root, today=None):
    """The label text, unescaped."""
    try:
        month = date.fromisoformat(latest_month(data_root) + "-01")
        loaded = last_ingest(data_root)
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        return cfg["freshness_missing"]
    n = max((((today or date.today())) - loaded).days, 0)
    return cfg["freshness"].format(
        month=f"{month:%B %Y}",
        loaded=loaded.isoformat(),
        days=f"{n} day" if n == 1 else f"{n} days",
    )
