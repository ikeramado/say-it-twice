"""Screens 2 and 3 of the site: the matrix of the 10 runs per case, one per agent, and the
trace behind each cell. Built from `runs/confirm-<agent>/outputs/` and `traces/`, the test
cases and the BTS flight record; no model call. The switch is CSS on radio inputs. Each trace is
a small HTML fragment, `traces/<agent>/<case_id>-<run>.html`, written by `write_traces`; a cell
links to its fragment's file, and the page's one script (`SCRIPT`) loads it into the placeholder
`#trace-<agent>-<case_id>-<run>` (shown by `:target`) so the page itself stays small."""

import csv
import html
import json
import os
from functools import cache
from pathlib import Path

from eval.confirm import mapped
from report.confirm import esc

AGENTS = ("naive", "cheap_strong", "system")
LABELS = {"naive": "Naive", "cheap_strong": "Cheap-strong", "system": "System"}
LETTER = {"refund": "R", "no_refund": "N", "escalate": "E"}
WORDS = {"refund": "refund", "no_refund": "no refund", "escalate": "escalate"}
RUNS = 10

CSS = """\
.switch input{position:absolute;opacity:0}
.switch label{display:inline-block;padding:.3rem .8rem;border:1px solid var(--line);cursor:pointer}
.switch input:focus-visible+label{outline:3px solid var(--mark)}
.mx{display:none}
.mx td,.mx th{text-align:center;padding:0}
.mx td:first-child,.mx th:first-child{text-align:left;padding:.1rem .4rem;white-space:nowrap}
.mx a{display:block;min-width:1.6rem;padding:.1rem .2rem;font-weight:bold;color:var(--ground);
text-decoration:none}
.d-refund{background:var(--refund)}.d-no_refund{background:var(--norefund)}.d-escalate{background:var(--escalate)}
.legend span{display:inline-block;margin-right:.8rem;padding:0 .4rem;border:1px solid var(--line)}
.trace{display:none;border:1px solid var(--line);padding:0 12px}
.trace:target{display:block}
.trace pre{white-space:pre-wrap;word-break:break-word;overflow-x:auto}
"""


def _css():
    sel = "".join(f"#sw-{a}:checked~.scroll .mx-{a}," for a in AGENTS).rstrip(",")
    chk = "".join(f"#sw-{a}:checked+label," for a in AGENTS).rstrip(",")
    return CSS + sel + "{display:table}\n" + chk + "{background:var(--mark);color:var(--ground)}\n"


def _read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


class MissingRuns(Exception):
    pass


def case_ids(cases, report):
    """The included test cases in file order: those the report did not exclude."""
    gone = {
        i for e in (report.get("exclusions") or {}).values() for i in e.get("ids", [])
    }
    return [c for c in cases if c["case_id"] not in gone]


@cache
def _month(flights_dir, month):
    path = Path(flights_dir) / f"{month}.csv"
    if not path.exists():
        return ()
    with path.open(newline="") as f:
        return tuple(csv.DictReader(f))


def flight_record(case, flights_dir):
    """The BTS row of the case's `bts_flight`, or None."""
    b = case.get("bts_flight")
    if not b:
        return None
    for r in _month(str(flights_dir), b["date"][:7]):
        if (r["carrier"], r["flight_number"], r["date"], r["origin"]) == (
            b["carrier"],
            str(b["flight_number"]),
            b["date"],
            b["origin"],
        ):
            return r
    return None


def collect(runs_dir, cases, flights_dir):
    """{agent: {case_id: [run record]*10}} plus the flight records by case id. A run record has
    the mapped decision, the raw output (None when the file is unreadable) and the trace.
    An agent whose `confirm-<agent>` dir is absent maps to None (no matrix); a dir with a
    missing outputs file raises `MissingRuns` naming the files."""
    data = {}
    missing = []
    for a in AGENTS:
        base = Path(runs_dir) / f"confirm-{a}"
        if not base.is_dir():
            data[a] = None
            continue
        per = {}
        for c in cases:
            runs = []
            for n in range(RUNS):
                name = f"{c['case_id']}_{n}.json"
                if not (base / "outputs" / name).exists():
                    missing.append(f"confirm-{a}/outputs/{name}")
                out = _read(base / "outputs" / name)
                runs.append(
                    {
                        "decision": mapped(out) if out else "escalate",
                        "out": out,
                        "trace": _read(base / "traces" / name),
                    }
                )
            per[c["case_id"]] = runs
        data[a] = per
    if missing:
        raise MissingRuns(
            f"{len(missing)} run output files are missing, e.g. "
            + ", ".join(missing[:5])
        )
    flights = {c["case_id"]: flight_record(c, flights_dir) for c in cases}
    return {"cases": cases, "runs": data, "flights": flights}


def build_data(runs_dir, cases_path, report, flights_dir=None):
    cases = [
        json.loads(x) for x in Path(cases_path).read_text().splitlines() if x.strip()
    ]
    flights_dir = flights_dir or (
        Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or Path(cases_path).parents[2])
        / "data/clean/flights"
    )
    return collect(runs_dir, case_ids(cases, report), flights_dir)


def anchor(agent, case_id, run):
    return f"trace-{agent}-{case_id}-{run}"


def fragment(agent, case_id, run):
    """The trace fragment's path under the site root."""
    return f"traces/{agent}/{case_id}-{run}.html"


# The one script of the site (cases.html): a click on a cell, or a `#trace-...` address, loads
# the run's fragment into its placeholder. With no script the cell links to the fragment file.
SCRIPT = """\
(function(){
function load(a,c,n){var d=document.getElementById("trace-"+a+"-"+c+"-"+n);
if(!d||d.getAttribute("data-done"))return;
fetch("traces/"+a+"/"+c+"-"+n+".html").then(function(r){if(!r.ok)throw 0;return r.text()})
.then(function(t){d.innerHTML=t;d.setAttribute("data-done","1")}).catch(function(){})}
function hash(){var m=/^#trace-([a-z_]+)-(.+)-(\\d+)$/.exec(location.hash);if(m)load(m[1],m[2],m[3])}
document.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest("a");
var m=a&&/^traces\\/([a-z_]+)\\/(.+)-(\\d+)\\.html$/.exec(a.getAttribute("href"));
if(!m)return;e.preventDefault();load(m[1],m[2],m[3]);
location.hash="trace-"+m[1]+"-"+m[2]+"-"+m[3]});
window.addEventListener("hashchange",hash);hash()})();
"""


def screen_matrix(report, cfg):
    m = cfg.get("_matrix")
    if not m:
        return None
    have = [a for a in AGENTS if m["runs"][a] is not None]
    gone = [LABELS[a] for a in AGENTS if m["runs"][a] is None]
    note = (
        f"<p>No matrix for {esc(', '.join(gone))}: its confirmatory run is not here.</p>"
        if gone
        else ""
    )
    sw = "".join(
        f'<input type="radio" name="agent" id="sw-{a}"{" checked" if a == have[0] else ""}>'
        f'<label for="sw-{a}">{esc(LABELS[a])}</label>'
        for a in have
    )
    head = "".join(f"<th>{n}</th>" for n in range(RUNS))
    tables = []
    for a in have:
        rows = []
        for c in m["cases"]:
            cells = "".join(
                f'<td class="d-{r["decision"]}"><a href="{fragment(a, c["case_id"], n)}" '
                f'aria-label="{esc(c["case_id"])} run {n}: {WORDS[r["decision"]]}">'
                f"{LETTER[r['decision']]}</a></td>"
                for n, r in enumerate(m["runs"][a][c["case_id"]])
            )
            rows.append(f'<tr><th scope="row">{esc(c["case_id"])}</th>{cells}</tr>')
        tables.append(
            f'<table class="mx mx-{a}" aria-label="{esc(LABELS[a])}, '
            f'{len(m["cases"])} cases, {RUNS} runs"><tr><th>Case</th>{head}</tr>'
            + "".join(rows)
            + "</table>"
        )
    return (
        f"<style>{_css()}</style>"
        "<p>One row per test case, one column per run. Pick an agent; a cell opens the trace "
        "of that run below.</p>"
        f'<div class="switch" role="group" aria-label="Agent">{sw}'
        + '<div class="scroll">'
        + "".join(tables)
        + "</div></div>"
        + note
        + '<p class="legend"><span class="d-refund">R refund</span>'
        '<span class="d-no_refund">N no refund</span>'
        '<span class="d-escalate">E escalate (also a failed or unreadable run)</span></p>'
    )


def _pre(obj):
    if isinstance(obj, str):
        return f"<pre>{esc(obj)}</pre>"
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return f"<pre>{html.escape(text, quote=False)}</pre>"


def _trace_html(agent, case, n, r, flight):
    out = r["out"] or {}
    raw = out.get("decision")
    dec = r["decision"]
    facts = case.get("facts") or {}
    fact_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(json.dumps(v.get('value')))}</td>"
        f"<td>{'constructed' if v.get('constructed') else 'from BTS'}</td></tr>"
        for k, v in sorted(facts.items())
    )
    fl = (
        "<table>"
        + "".join(
            f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in flight.items()
        )
        + "</table>"
        if flight
        else "<p>No BTS flight record for this case.</p>"
    )
    if r["out"] is None:
        why = " (the run file is unreadable; mapped to escalate)"
    elif raw == dec:
        why = ""
    else:
        why = f" (the run gave {esc(raw)}; mapped to escalate)"
    tr = r["trace"]
    if tr is None:
        steps = "<p>No trace file.</p>"
    else:
        items = tr if isinstance(tr, list) else [tr]
        slim = [
            {
                k: v
                for k, v in i.items()
                if k not in ("prompt", "prefix_sha256", "id", "sample")
            }
            for i in items
        ]
        for i in slim[1:]:  # the prompt hashes are the same for each call of a run
            i.pop("prompts_sha256", None)
        steps = _pre(slim)
    return (
        f"<h3>{esc(LABELS[agent])}, {esc(case['case_id'])}, run {n}</h3>"
        f"<p>Decision: <strong>{esc(WORDS[dec])}</strong>{why}</p>"
        f"<p>Rule version in force: {esc(out.get('rule_version') or 'not available')}<br>"
        f"Airline policy version: {esc(out.get('policy_version') or 'not available')}<br>"
        f"Clause: {esc(out.get('clause') or 'not available')}</p>"
        f"<p>Explanation: {esc(out.get('explanation') or 'not available')}</p>"
        f"<h4>Flight record (BTS)</h4>{fl}"
        f"<h4>Facts</h4><table>{fact_rows}</table>"
        f"<h4>Trace</h4>{steps}"
    )


def screen_trace(report, cfg):
    m = cfg.get("_matrix")
    if not m:
        return None
    parts = [
        (
            "<p>Pick a cell in the matrix above to show its trace here: the flight record, "
            "the rule and airline policy versions, the clause, the decision, the "
            "explanation, and which facts are constructed. Each trace is its own small file, "
            "loaded when you pick it.</p>"
        )
    ]
    for a in AGENTS:
        if m["runs"][a] is None:
            continue
        for c in m["cases"]:
            for n in range(RUNS):
                parts.append(
                    f'<div class="trace" id="{anchor(a, c["case_id"], n)}">'
                    f'<a href="{fragment(a, c["case_id"], n)}">trace of this run</a></div>'
                )
    return "".join(parts)


def write_traces(out, cfg):
    """One fragment file per (agent, case, run) of the matrix; returns how many."""
    m = cfg.get("_matrix")
    if not m:
        return 0
    count = 0
    for a in AGENTS:
        if m["runs"][a] is None:
            continue
        d = Path(out) / "traces" / a
        d.mkdir(parents=True, exist_ok=True)
        for c in m["cases"]:
            for n, r in enumerate(m["runs"][a][c["case_id"]]):
                (Path(out) / fragment(a, c["case_id"], n)).write_text(
                    _trace_html(a, c, n, r, m["flights"][c["case_id"]])
                )
                count += 1
    return count
