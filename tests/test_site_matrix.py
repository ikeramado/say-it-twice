import csv
import json
import os
import re
from pathlib import Path

import pytest

from report.site import ROOT, build
from report.site.matrix import AGENTS, MissingRuns

FIX = Path(__file__).parent / "fixtures" / "site" / "report.json"
CONFIG = ROOT / "config" / "site.yaml"
DECS = ["refund", "no_refund", "escalate"]
LET = {"refund": "R", "no_refund": "N", "escalate": "E"}
CASES = ["c-a", "c-b"]
FAILED = ("naive", "c-a", 3)


def decision(agent, cid, n):
    if (agent, cid, n) == FAILED:
        return "refund"  # the file says refund but the run failed: maps to escalate
    return DECS[(n + len(cid) + AGENTS.index(agent) + CASES.index(cid)) % 3]


def expected(agent, cid, n):
    return "escalate" if (agent, cid, n) == FAILED else decision(agent, cid, n)


def trace_for(a, cid, n):
    if a == "system":
        return [
            {
                "id": "x",
                "sample": 0,
                "prompt": "SECRETPROMPT",
                "prefix_sha256": "PFXHASH",
                "prompts_sha256": {"s.txt": "HASH-S"},
                "tool_calls": [{"tool": "get_rule", "result": f"v-{cid}-{n}"}],
                "facts": {"cancelled": False},
                "engine": {"decision": "refund", "clause": f"eng-{cid}-{n}"},
                "triggers": [f"trig-{n}"],
            }
        ]
    return [
        {
            "id": f"i{k}",
            "sample": k,
            "prompt": "SECRETPROMPT",
            "prefix_sha256": "PFXHASH",
            "prompts_sha256": {"n.txt": f"HASH-{a}"},
            "answer": f"raw {a} {cid} {n}",
        }
        for k in range(2)
    ]


def write_tree(t, agents=AGENTS):
    cases = [
        {
            "case_id": cid,
            "bts_flight": {
                "carrier": "DL",
                "date": "2024-04-30",
                "flight_number": str(100 + i),
                "origin": "ORD",
            },
            "facts": {
                "arrival_delay_min": {"value": 180 + i, "constructed": False},
                "purchase_date": {"value": "2024-04-17", "constructed": True},
            },
        }
        for i, cid in enumerate(CASES)
    ]
    (t / "cases.jsonl").write_text("\n".join(json.dumps(c) for c in cases))
    fl = t / "fl"
    fl.mkdir()
    with (fl / "2024-04.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["carrier", "flight_number", "date", "origin", "arrival_delay"])
        w.writerow(["DL", "100", "2024-04-30", "ORD", "181"])
        w.writerow(["DL", "101", "2024-04-30", "ORD", "999"])
    for a in agents:
        for sub in ("outputs", "traces"):
            (t / "runs" / f"confirm-{a}" / sub).mkdir(parents=True)
        for cid in CASES:
            for n in range(10):
                d = decision(a, cid, n)
                out = {
                    "case_id": cid,
                    "run": n,
                    "decision": d,
                    "clause": f"clause-{a}-{cid}-{n}",
                    "rule_version": f"rv-{n}",
                    "policy_version": f"pv-{n}",
                    "explanation": f"why {a} {cid} {n}",
                    "network_error": (a, cid, n) == FAILED,
                }
                name = f"{cid}_{n}.json"
                base = t / "runs" / f"confirm-{a}"
                (base / "outputs" / name).write_text(json.dumps(out))
                (base / "traces" / name).write_text(json.dumps(trace_for(a, cid, n)))
    rep = json.loads(FIX.read_text())
    rep["exclusions"] = {}
    (t / "report.json").write_text(json.dumps(rep))
    return t / "report.json", fl


class Built(str):
    """The text of cases.html; `.site` is the built site (its trace fragments are files)."""


def run_build(t, fl):
    site = t / "site"
    build(site, t / "report.json", CONFIG, t / "runs", t / "cases.jsonl", fl)
    built = Built((site / "cases.html").read_text())
    built.site = site
    return built


def trace(built, agent, case_id, n):
    """The fragment file of one run's trace."""
    return (built.site / "traces" / agent / f"{case_id}-{n}.html").read_text()


def all_traces(built):
    return "".join(f.read_text() for f in sorted((built.site / "traces").rglob("*.html")))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = tmp_path_factory.mktemp("mx")
    _, fl = write_tree(t)
    return run_build(t, fl)


def test_absent_agent_dir_gets_no_matrix_and_says_so(tmp_path):
    _, fl = write_tree(tmp_path, ("naive", "system"))
    html = run_build(tmp_path, fl)
    assert 'class="mx mx-naive"' in html and 'class="mx mx-system"' in html
    assert 'class="mx mx-cheap_strong"' not in html
    assert "No matrix for Cheap-strong: its confirmatory run is not here." in html
    assert 'id="trace-cheap_strong-' not in html


def test_missing_output_file_fails_the_build_naming_it(tmp_path):
    _, fl = write_tree(tmp_path)
    (tmp_path / "runs/confirm-system/outputs/c-b_4.json").unlink()
    with pytest.raises(MissingRuns, match=r"confirm-system/outputs/c-b_4\.json"):
        run_build(tmp_path, fl)


def test_unreadable_output_file_maps_to_escalate(tmp_path):
    _, fl = write_tree(tmp_path)
    (tmp_path / "runs/confirm-system/outputs/c-b_4.json").write_text("{not json")
    html = run_build(tmp_path, fl)
    tbl = re.search(r'<table class="mx mx-system".*?</table>', html, re.DOTALL).group(0)
    row = re.search(r'<th scope="row">c-b</th>(.*?)</tr>', tbl, re.DOTALL).group(1)
    cells = re.findall(r'<td class="d-(\w+)"><a href="([^"]+)"[^>]*>(\w)</a>', row)
    assert cells[4] == ("escalate", "traces/system/c-b-4.html", "E")
    blk = trace(html, "system", "c-b", 4)
    assert "(the run file is unreadable; mapped to escalate)" in blk
    assert "None" not in blk.split("<h4>Flight")[0]


def test_system_trace_fields_show(built):
    blk = trace(built, "system", "c-a", 2)
    tr = blk.split("<h4>Trace</h4>")[1]
    for want in (
        "tool_calls",
        "get_rule",
        "v-c-a-2",
        "facts",
        "engine",
        "eng-c-a-2",
        "triggers",
        "trig-2",
    ):
        assert want in tr


def test_dropped_fields_absent_and_hash_once_per_run(built):
    for a in AGENTS:
        blk = trace(built, a, "c-a", 1)
        tr = blk.split("<h4>Trace</h4>")[1]
        for gone in ("SECRETPROMPT", "PFXHASH", "&quot;id&quot;", '"id"', '"sample"'):
            assert gone not in tr
        assert tr.count("prompts_sha256") == 1
    assert "HASH-naive" in all_traces(built)
    assert 'raw naive c-a 1"' in all_traces(built) or "raw naive c-a 1" in all_traces(built)


# @criterion C10
def test_matrix_letters_per_cell_and_failed_run(built):
    for a in AGENTS:
        tbl = re.search(
            rf'<table class="mx mx-{a}".*?</table>', built, re.DOTALL
        ).group(0)
        for cid in CASES:
            row = re.search(
                rf'<th scope="row">{cid}</th>(.*?)</tr>', tbl, re.DOTALL
            ).group(1)
            cells = re.findall(
                r'<td class="d-(\w+)"><a href="([^"]+)"[^>]*>(\w)</a>', row
            )
            assert len(cells) == 10
            for n, (cls, href, letter) in enumerate(cells):
                e = expected(a, cid, n)
                assert (cls, letter) == (e, LET[e])
                assert href == f"traces/{a}/{cid}-{n}.html"
                assert f'<div class="trace" id="trace-{a}-{cid}-{n}">' in built


# @criterion C10
def test_switch_names_three_agents(built):
    for a, name in zip(AGENTS, ("Naive", "Cheap-strong", "System")):
        assert f'<label for="sw-{a}">{name}</label>' in built


# @criterion C10
def test_trace_is_that_runs_own(built):
    for a in AGENTS:
        for cid, n in (("c-a", 3), ("c-b", 7)):
            blk = trace(built, a, cid, n)
            assert f"Clause: clause-{a}-{cid}-{n}<" in blk
            assert f"Explanation: why {a} {cid} {n}<" in blk
            assert f"Rule version in force: rv-{n}<" in blk
            assert f"Airline policy version: pv-{n}<" in blk
            assert (a == "system") or f"raw {a} {cid} {n}" in blk
    blk = trace(built, "naive", "c-a", 3)
    assert "Decision: <strong>escalate</strong> (the run gave refund" in blk


def test_flight_record_and_constructed_facts(built):
    blk = trace(built, "system", "c-b", 0)
    assert "<td>arrival_delay</td><td>999</td>" in blk
    assert (
        "<td>purchase_date</td><td>&quot;2024-04-17&quot;</td><td>constructed</td>"
        in blk
    )
    assert "<td>arrival_delay_min</td><td>181</td><td>from BTS</td>" in blk


REAL = Path(os.environ.get("SAY_IT_TWICE_RUNS", ROOT / "runs"))


@pytest.mark.skipif(
    not (REAL / "confirm-system").exists()
    or not (REAL / "confirm/report.json").exists(),
    reason="no runs/confirm-system or runs/confirm/report.json",
)
def test_real_matrix_rows_and_cells(tmp_path):
    rep = json.loads((REAL / "confirm/report.json").read_text())
    root = Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT)
    build(
        tmp_path,
        REAL / "confirm/report.json",
        CONFIG,
        REAL,
        ROOT / "cases/test/cases.jsonl",
        root / "data/clean/flights",
    )
    html = (tmp_path / "cases.html").read_text()
    for a in AGENTS:
        tbl = re.search(rf'<table class="mx mx-{a}".*?</table>', html, re.DOTALL).group(
            0
        )
        rows = re.findall(r'<th scope="row">.*?</tr>', tbl, re.DOTALL)
        assert len(rows) == rep["cases"]
        assert all(r.count("<td") == 10 for r in rows)
