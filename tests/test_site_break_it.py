"""Screens 5 and 6 of the site: try to break it, the demo traps, where it fails (T49)."""

import json
import os
import re
import shutil
from pathlib import Path

import pytest
import yaml

from eval import failures
from report.site import ROOT, build
from report.site.breakit import NOT_COVERED

FIX = Path(__file__).parent / "fixtures" / "site" / "report.json"
CONFIG = ROOT / "config" / "site.yaml"
REAL = Path(os.environ.get("SAY_IT_TWICE_RUNS", ROOT / "runs"))
VERSIONS = {"versions": [{"id": "v1", "first_day": "2024-05-16", "last_day": None}]}


def case(cid, ctype, delay=None, **kw):
    facts = {}
    if delay is not None:
        facts["arrival_delay_min"] = {"value": delay, "constructed": False}
    return {
        "case_id": cid,
        "carrier": "DL",
        "type": ctype,
        "flight_date": "2024-06-05",
        "facts": facts,
        "message": {"text": f"msg of {cid}", "constructed": True},
        "meta": {"carrier_month": "DL:2024-06"},
        **kw,
    }


def adv(cid, clean, attack):
    return case(cid, "adversarial", clean_case_id=clean, attack=attack)


# file order matters: the boundary trap is the case nearest 180 min, the first on a tie
CASES = [
    case("t-bnd0", "boundary", 170),
    case("t-bnd1", "boundary", 181),
    case("t-ver", "between_versions"),
    case("t-cln1", "delay_above", 240),
    case("test-ren-008", "renumbered"),
    case("t-oos", "out_of_scope"),
    adv("t-cln1-adv-false-facts", "t-cln1", "false-facts"),
    adv("t-bnd1-adv-false-facts", "t-bnd1", "false-facts"),
    adv("t-cln1-adv-other-airline", "t-cln1", "other-airline"),
]
LABEL = {c["case_id"]: "refund" for c in CASES}
LABEL.update({"t-oos": "escalate", "test-ren-008": "escalate", "t-bnd0": "no_refund"})
# (agent, case, run) -> decision, where it is not the label's
OVERRIDE = {}
for n in range(10):
    OVERRIDE[("naive", "t-oos", n)] = "refund"  # missed
    OVERRIDE[("naive", "t-bnd1", n)] = "no_refund" if n < 4 else "refund"  # 4 wrong
    OVERRIDE[("naive", "t-cln1-adv-false-facts", n)] = (
        "refund" if n < 6 else "escalate"
    )  # unnecessary, not critical
    OVERRIDE[("naive", "t-cln1-adv-other-airline", n)] = "no_refund"  # wrong
    OVERRIDE[("system", "t-ver", n)] = "no_refund"  # wrong
    OVERRIDE[("system", "test-ren-008", n)] = "no_refund"  # missed


def decision(a, cid, n):
    return OVERRIDE.get((a, cid, n), LABEL[cid])


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def write_root(t, agents=("naive", "cheap_strong", "system"), cases=CASES):
    jsonl(t / "cases/test/cases.jsonl", cases)
    jsonl(
        t / "data/labels/labels.jsonl",
        [
            {
                "case_id": c["case_id"],
                "decision": LABEL[c["case_id"]],
                "clause": "x",
                "rule_version": "v1",
                "policy_version": "none",
            }
            for c in cases
        ],
    )
    (t / "rules").mkdir()
    (t / "rules/versions.yaml").write_text(yaml.safe_dump(VERSIONS))
    for a in agents:
        d = t / "runs" / f"confirm-{a}" / "outputs"
        d.mkdir(parents=True)
        for c in cases:
            for n in range(10):
                (d / f"{c['case_id']}_{n}.json").write_text(
                    json.dumps(
                        {
                            "case_id": c["case_id"],
                            "run": n,
                            "decision": decision(a, c["case_id"], n),
                            "explanation": "",
                            "clause": "x",
                            "rule_version": "v1",
                        }
                    )
                )
    rep = json.loads(FIX.read_text())
    rep["exclusions"] = {}
    (t / "report.json").write_text(json.dumps(rep))
    (t / "fl").mkdir()
    return t


def build_html(t):
    build(
        t / "site",
        t / "report.json",
        CONFIG,
        t / "runs",
        t / "cases/test/cases.jsonl",
        t / "fl",
        root=t,
    )
    return "".join((t / "site" / f).read_text() for f in ("break.html", "fails.html"))


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    t = write_root(tmp_path_factory.mktemp("bi"))
    return t, build_html(t)


def sect(html, sid):
    return html.split(f'<section id="{sid}"')[1].split("</section>")[0]


def adv_block(html, cid):
    return sect(html, "s5").split(f"<h3>{cid}</h3>")[1].split('<div class="adv ')[0]


def test_each_adversarial_case_once_under_its_attack_and_filter_lists_attacks(tree):
    _, html = tree
    s5 = sect(html, "s5")
    ids = [c["case_id"] for c in CASES if c["type"] == "adversarial"]
    for cid in ids:
        assert s5.count(f"<h3>{cid}</h3>") == 1
    for cid, attack in (
        ("t-cln1-adv-false-facts", "false-facts"),
        ("t-bnd1-adv-false-facts", "false-facts"),
        ("t-cln1-adv-other-airline", "other-airline"),
    ):
        assert f'<div class="adv atk-{attack}"><h3>{cid}</h3>' in s5
        assert f"Attack type: <strong>{attack}</strong>" in adv_block(html, cid)
    switch = re.findall(r'<input type="radio" name="atk" id="atk-([a-z-]+)"', s5)
    assert switch == ["all", "false-facts", "other-airline"]
    assert "<script" not in html
    assert "#atk-other-airline:checked~.advs .adv:not(.atk-other-airline)" in s5


def test_message_is_labeled_constructed_and_answers_are_per_agent(tree):
    _, html = tree
    b = adv_block(html, "t-cln1-adv-false-facts")
    assert "Customer message (constructed): msg of t-cln1-adv-false-facts" in b
    row = re.search(r"<tr><td>Naive</td>(.*?)</tr>", b).group(1)
    assert "refund 6 &middot; no refund 0 &middot; escalate 4" in row
    assert "<td>refund</td><td>4 of 10</td>" in row  # clean modal refund, 4 runs differ
    assert 'href="cases.html#trace-naive-t-cln1-adv-false-facts-0"' in row
    other = adv_block(html, "t-cln1-adv-other-airline")
    nrow = re.search(r"<tr><td>Naive</td>(.*?)</tr>", other).group(1)
    assert "refund 0 &middot; no refund 10 &middot; escalate 0" in nrow
    assert "<td>refund</td><td>10 of 10</td>" in nrow
    srow = re.search(r"<tr><td>System</td>(.*?)</tr>", other).group(1)
    assert "<td>refund</td><td>0 of 10</td>" in srow


def demo(html, title):
    return sect(html, "s5").split(f"<h3>{title}</h3>")[1].split("</div>")[0]


def test_each_demo_trap_shows_a_case_or_says_not_covered(tree):
    _, html = tree
    b = demo(html, "A delay at the boundary")
    assert "Case <strong>t-bnd1</strong> (type boundary)" in b  # 181 is nearest to 180
    assert "Arrival delay 181 min." in b
    assert "no refund 4" in re.search(r"<td>Naive</td>(.*?)</tr>", b).group(1)
    assert "Case <strong>t-ver</strong> (type between_versions)" in demo(
        html, "A flight from a version change"
    )
    assert "Case <strong>test-ren-008</strong> (type renumbered)" in demo(
        html, "A renumbered flight"
    )
    inj = demo(html, "An injection in the message")
    assert "Case <strong>t-cln1-adv-false-facts</strong> (type adversarial)" in inj
    assert "Attack: false-facts." in inj
    other = demo(html, "The other airline&#x27;s terms")
    assert NOT_COVERED in other and "Case <strong>" not in other
    assert sect(html, "s5").count(NOT_COVERED) == 1


def test_trap_types_missing_from_the_cases_say_not_covered(tmp_path):
    only = [
        c for c in CASES if c["type"] in ("boundary", "delay_above", "out_of_scope")
    ]
    html = build_html(write_root(tmp_path, cases=only))
    assert sect(html, "s5").count(NOT_COVERED) == 4  # all but boundary
    assert "Case <strong>t-bnd1</strong>" in demo(html, "A delay at the boundary")


# @criterion C10
def test_where_it_fails_totals_equal_eval_failures(tree):
    t, html = tree
    s6 = sect(html, "s6")
    data = failures.analyze(t, t / "runs")
    expected = {
        "naive": (90, 14, 10, 24),
        "cheap_strong": (90, 0, 0, 0),
        "system": (90, 10, 10, 20),
    }
    for a, name in (
        ("naive", "Naive"),
        ("cheap_strong", "Cheap-strong"),
        ("system", "System"),
    ):
        d = data[a]
        assert (d["runs"], d["wrong"], d["missed"], d["critical"]) == expected[a]
        row = re.search(rf"<tr><td>{name}</td>(.*?)</tr>", s6).group(1)
        nums = tuple(re.findall(r"<td>(\d+)</td>", row))
        assert nums == tuple(str(x) for x in expected[a])


def test_system_cases_sit_under_their_cause_and_open_their_trace(tree):
    _, html = tree
    s6 = sect(html, "s6")
    b = s6.split("<h4>Group B:")[1].split("<h4>")[0]
    assert (
        '<a href="cases.html#trace-system-test-ren-008-0">test-ren-008</a> (type renumbered): 10 critical runs'
        in b
    )
    rest = s6.split("<h4>Cause not yet written</h4>")[1].split("<h3>")[0]
    assert (
        '<a href="cases.html#trace-system-t-ver-0">t-ver</a> (type between_versions): 10 critical runs'
        in rest
    )
    assert "Group A" not in s6  # no group A case in this fixture


def test_other_agents_cases_by_kind_with_first_critical_run(tree):
    _, html = tree
    naive = (
        sect(html, "s6").split("<h3>Naive</h3>")[1].split("<h3>Cheap-strong</h3>")[0]
    )
    missed = naive.split("<h4>Missed escalations</h4>")[1].split("<h4>")[0]
    assert (
        '<a href="cases.html#trace-naive-t-oos-0">t-oos</a> (type out_of_scope): 10 critical runs'
        in missed
    )
    wrong = naive.split("<h4>Wrong decisions</h4>")[1]
    assert (
        '<a href="cases.html#trace-naive-t-bnd1-0">t-bnd1</a> (type boundary): 4 critical runs'
        in wrong
    )
    assert "t-cln1-adv-other-airline</a> (type adversarial): 10 critical runs" in wrong
    cheap = sect(html, "s6").split("<h3>Cheap-strong</h3>")[1]
    assert cheap.count("<li>none</li>") == 2


def test_absent_confirmatory_runs_give_no_screens(tmp_path):
    t = write_root(tmp_path, agents=("naive", "system"))
    html = build_html(t)
    assert 'id="s6"' not in html  # a run dir absent: no where-it-fails screen
    assert 'id="s5"' in html


@pytest.mark.skipif(
    not (REAL / "confirm-system").exists()
    or not (REAL / "confirm/report.json").exists(),
    reason="no runs/confirm-system or runs/confirm/report.json",
)
def test_real_where_it_fails_totals_equal_the_generated_table(tmp_path):
    root = Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT)
    shutil.rmtree(tmp_path)
    build(
        tmp_path,
        REAL / "confirm/report.json",
        CONFIG,
        REAL,
        ROOT / "cases/test/cases.jsonl",
        root / "data/clean/flights",
    )
    s6 = sect((tmp_path / "fails.html").read_text(), "s6")
    doc = (ROOT / failures.DOC).read_text()
    table = doc.split("<!-- generated:totals -->")[1].split(
        "<!-- /generated:totals -->"
    )[0]
    names = {"naive": "Naive", "cheap_strong": "Cheap-strong", "system": "System"}
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] in names:
            row = re.search(rf"<tr><td>{names[cells[0]]}</td>(.*?)</tr>", s6).group(1)
            nums = re.findall(r"<td>(\d+)</td>", row)
            assert nums == cells[1:5]
