"""Screen 4 of the site: the rule versions v0 to v4 on a timeline, Delta's flights of July 2024
placed on it, and a date toggle for a few fixed real flights.

Everything is computed at build time from `rules.lookup` and the rule engine; no model call, no
script (the toggle is CSS on radio inputs, as the matrix's agent switch). A flight's real facts
(cancelled, arrival delay) come from its BTS row in `<flights_dir>/2024-07.csv`; the facts BTS
does not hold are constructed here and labeled so on the page. The policy is Delta's version
for a purchase 30 days before the flight, held fixed while the date moves.
"""

import csv
from datetime import date, timedelta
from pathlib import Path

from agents.system import engine
from report.confirm import esc
from report.site.matrix import WORDS
from rules.lookup import Exclusion, policy_for, rule_for, rule_versions

CARRIER = "DL"
PURCHASE_DAYS_BEFORE = 30
# The date positions the visitor moves across; one per version, in order. The version of each
# comes from rules.lookup, not from this list.
POSITIONS = (
    date(2024, 3, 1),
    None,  # the flight's own real date
    date(2025, 3, 1),
    date(2026, 1, 15),
    date(2026, 8, 1),
)
# Real Delta flights of the CrowdStrike meltdown (BTS, 2024-07). `renumbered` is constructed.
EXAMPLES = (
    {"number": "31", "origin": "ATL", "date": "2024-07-19", "renumbered": False},
    {"number": "32", "origin": "DFW", "date": "2024-07-19", "renumbered": False},
    {"number": "300", "origin": "ATL", "date": "2024-07-20", "renumbered": True},
)

CSS = """\
.tl{list-style:none;padding:0;border-left:4px solid var(--line);margin:1rem 0}
.tl li{padding:.2rem 0 .6rem 12px}
.tl .fl{font-size:.9rem;margin:.2rem 0 0}
.tlx{margin:1.5rem 0}
.tlx input{position:absolute;opacity:0}
.tlx label{display:inline-block;padding:.3rem .8rem;border:1px solid var(--line);cursor:pointer;
margin:0 .3rem .3rem 0}
.tlx input:focus-visible+label{outline:3px solid var(--mark)}
.tlp{display:none;border:1px solid var(--line);padding:0 12px}
.cons{font-style:italic}
"""


def _row(flights_dir, ex):
    path = Path(flights_dir) / f"{ex['date'][:7]}.csv"
    if not path.exists():
        return None
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            if (r["carrier"], r["flight_number"], r["date"], r["origin"]) == (
                CARRIER,
                ex["number"],
                ex["date"],
                ex["origin"],
            ):
                return r
    return None


def _facts(row, ex):
    """(engine facts, [(name, value, constructed)]) for one example."""
    real = [("cancelled", row["cancelled"] == "1")]
    if row["arrival_delay"] != "":
        real.append(("arrival_delay_min", int(row["arrival_delay"])))
    flight = date.fromisoformat(ex["date"])
    made = [
        ("purchase_date", (flight - timedelta(days=PURCHASE_DAYS_BEFORE)).isoformat()),
        ("alternative_accepted", False),
        ("renumbered", ex["renumbered"]),
    ]
    if ex["renumbered"]:
        made.append(("significant_change", False))
    listed = [(k, v, False) for k, v in real] + [(k, v, True) for k, v in made]
    return {k: v for k, v, _ in listed}, listed


def build_timeline(flights_dir):
    """The data of screen 4: {"versions": [...], "examples": [...]}. An example whose BTS row
    is absent from `flights_dir` is left out."""
    examples = []
    for ex in EXAMPLES:
        row = _row(flights_dir, ex)
        if row is None:
            continue
        facts, listed = _facts(row, ex)
        flight = date.fromisoformat(ex["date"])
        pol = policy_for(CARRIER, date.fromisoformat(facts["purchase_date"]))
        positions = []
        for p in POSITIONS:
            day = p or flight
            rule = rule_for(day, ex["renumbered"])
            res = engine.decide(facts, rule, pol)
            positions.append(
                {
                    "date": day.isoformat(),
                    "real": p is None,
                    "rule_version": res["rule_version"],
                    "decision": res["decision"],
                    "clause": res["clause"],
                    "policy_version": res["policy_version"],
                    "excluded": rule.reason if isinstance(rule, Exclusion) else None,
                }
            )
        examples.append(
            {
                "label": f"{CARRIER} {ex['number']} {ex['origin']}, {ex['date']}",
                "flight_version": rule_for(flight, False).id,
                "listed": listed,
                "positions": positions,
            }
        )
    return examples


def _span(v):
    return f"{v.first_day} to {v.last_day or 'today, no end date'}"


def _value(v):
    return "yes" if v is True else "no" if v is False else str(v)


def _facts_html(listed):
    items = "".join(
        f"<li{' class=cons' if c else ''}>{esc(k)}: {esc(_value(v))} "
        f"({'constructed for this page' if c else 'from BTS'})</li>"
        for k, v, c in listed
    )
    return f"<ul>{items}</ul>"


def _css(examples):
    sel = ",".join(
        f"#tl-{i}-{k}:checked~.tlps .tlp-{i}-{k}"
        for i, ex in enumerate(examples)
        for k in range(len(ex["positions"]))
    )
    chk = ",".join(
        f"#tl-{i}-{k}:checked+label"
        for i, ex in enumerate(examples)
        for k in range(len(ex["positions"]))
    )
    return CSS + sel + "{display:block}\n" + chk + "{background:var(--mark);color:var(--ground)}\n"


def _example_html(i, ex):
    radios, panels = "", ""
    for k, p in enumerate(ex["positions"]):
        ver = p["rule_version"] or "excluded"
        real = " (the flight's real date)" if p["real"] else ""
        radios += (
            f'<input type="radio" name="tl-{i}" id="tl-{i}-{k}"{" checked" if k == 0 else ""}>'
            f'<label for="tl-{i}-{k}">{esc(p["date"])} &middot; {esc(ver)}</label>'
        )
        why = f"<p>{esc(p['excluded'])}</p>" if p["excluded"] else ""
        panels += (
            f'<div class="tlp tlp-{i}-{k}"><h4>Date {esc(p["date"])}{real}</h4>'
            f"<p>Version in force: <strong>{esc(ver)}</strong></p>"
            f"<p>Engine decision: <strong>{esc(WORDS[p['decision']])}</strong>, "
            f"clause {esc(p['clause'])}, airline policy {esc(p['policy_version'])}</p>"
            f"{why}</div>"
        )
    return (
        f'<div class="tlx" role="group" aria-label="{esc(ex["label"])}">'
        f"<h3>{esc(ex['label'])}</h3>{_facts_html(ex['listed'])}"
        f'{radios}<div class="tlps">{panels}</div></div>'
    )


def screen_timeline(report, cfg):
    examples = cfg.get("_timeline")
    if examples is None:
        return None
    by_version = {}
    for ex in examples:
        by_version.setdefault(ex["flight_version"], []).append(ex["label"])
    items = ""
    for v in rule_versions():
        files = ", ".join(esc(Path(s).name) for s in v.source_files)
        fl = by_version.get(v.id)
        fls = (
            f'<p class="fl">Delta flights of July 2024 here: {esc("; ".join(fl))}</p>'
            if fl
            else ""
        )
        items += (
            f"<li><strong>{esc(v.id)}</strong>, effective {esc(_span(v))}"
            f'<br><span class="fl">Source: {files}</span>{fls}</li>'
        )
    note = (
        "<p>Flights of 2024-07-01 to 2024-07-31 are rows of the BTS on-time data. The facts BTS "
        "does not hold are constructed for this page and marked so: each purchase date is "
        f"{PURCHASE_DAYS_BEFORE} days before its flight, the passenger accepts no alternative, "
        "and whether the flight was renumbered is set per example. The airline policy is "
        "Delta's version for that purchase date and does not move with the date; only the "
        "date, and with it the rule version in force, does. Every decision is the rule "
        "engine's, computed when the page was built.</p>"
    )
    if not examples:
        return (
            f'<ol class="tl">{items}</ol>'
            "<p>The July 2024 flights are not in this build: the BTS file was not found.</p>"
        )
    return (
        f'<style>{_css(examples)}</style><ol class="tl">{items}</ol>{note}'
        + "".join(_example_html(i, ex) for i, ex in enumerate(examples))
    )
