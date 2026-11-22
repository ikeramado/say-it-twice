"""The story page (T61): the six blocks in order, every figure equal to the value its module
computes on the same fixture, the answer squares, the statute quote, the evidence links, the
size and the hosts. The real-data test reads SAY_IT_TWICE_RUNS and SAY_IT_TWICE_DATA_ROOT."""

import copy
import csv
import os
import re
from pathlib import Path

import pytest
import yaml

from eval import delays, fixed_rule
from report import confirm as rc
from report.site import ROOT, build, clause_text
from tests.test_confirm_report import build as build_tree
from tests.test_delays import CASES, DECISIONS, LABEL

FIX = Path(__file__).parent / "fixtures" / "site"
CONFIG = ROOT / "config" / "site.yaml"
NAIVE_FIRST = "RNNRNRNNNR"


def flight_case(c, origin, number, delay, **extra):
    c = copy.deepcopy(c)
    c.update(origin=origin, flight_number=number, **extra)
    c["bts_flight"] = {
        "carrier": c["carrier"],
        "date": c["flight_date"],
        "flight_number": number,
        "origin": origin,
    }
    c["facts"]["arrival_delay_min"] = {"value": delay, "constructed": False}
    c["facts"]["purchase_date"] = {"value": "2024-06-20", "constructed": True}
    return c


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    t = tmp_path_factory.mktemp("story")
    cases = copy.deepcopy(CASES)
    for i, c in enumerate(cases):
        if c["case_id"] == "r1":
            cases[i] = flight_case(
                c, "CID", "1039", -14, message={"text": "I want my money back.", "constructed": True}
            )
        if c["case_id"] == "d1":
            cases[i] = flight_case(c, "ATL", "1832", 189)
    decisions = copy.deepcopy(DECISIONS)
    decisions["naive"]["r1"] = [{"R": "refund", "N": "no_refund"}[d] for d in NAIVE_FIRST]
    root = build_tree(t, cases, LABEL, decisions)
    rc.main(["--root", str(root), "--runs-dir", str(root / "runs")])
    fl = root / "fl"
    fl.mkdir()
    with (fl / "2024-07.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["carrier", "flight_number", "date", "origin", "arrival_delay", "cancelled"])
        w.writerow(["AA", "1039", "2024-07-01", "CID", "-14", "0"])
        w.writerow(["DL", "1832", "2024-07-01", "ATL", "189", "0"])
    with (fl / "2024-11.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["carrier", "flight_number", "date", "origin", "destination", "arrival_delay", "cancelled"])
        w.writerow(["DL", "1", "2024-11-02", "ATL", "JFK", "200", "0"])
        w.writerow(["AA", "2", "2024-11-03", "DFW", "ORD", "", "1"])
        w.writerow(["AA", "3", "2024-11-03", "DFW", "ORD", "20", "0"])
    cfg = yaml.safe_load(CONFIG.read_text())
    cfg["story"]["first_case"], cfg["story"]["second_case"] = "r1", "d1"
    (root / "site.yaml").write_text(yaml.safe_dump(cfg))
    fonts = root / "fonts-src"
    fonts.mkdir()
    (fonts / "Archivo-800.woff2").write_bytes(b"wOF2")
    (fonts / "OFL-Archivo.txt").write_text("SIL Open Font License")
    out = root / "site"
    build(
        out,
        root / "runs/confirm/report.json",
        root / "site.yaml",
        root / "runs",
        root / "cases/test/cases.jsonl",
        fl,
        root=root,
        chatbots_dir=FIX / "chatbots",
        fonts_dir=fonts,
    )
    return root, out, cfg, fl


def blocks(html):
    return re.findall(r"<section[ >].*?</section>", html, re.DOTALL)


def squares(block):
    return re.findall(r'<div class="sq (\w)( miss)?"', block)


# @criterion C10
# @criterion C14
def test_six_blocks_in_order_with_their_headings(tree):
    _, out, cfg, _ = tree
    html = (out / "index.html").read_text()
    heads = [
        "Same question, ten times",
        "We asked an AI agent the same question ten times.",
        "It was not one case",
        "Consistent is not the same as right",
        "With the rule fixed",
        "What a wrong answer costs",
        cfg["close_question"],
    ]
    pos = [html.index(h) for h in heads]
    assert pos == sorted(pos)
    assert len(blocks(html)) == 6


# @criterion C10
def test_figures_equal_the_values_their_modules_compute(tree):
    import json

    root, out, _, _ = tree
    html = (out / "index.html").read_text()
    rep = json.loads((root / "runs/confirm/report.json").read_text())
    for a in ("naive", "system"):
        assert f"{round(100 * rep['primary']['H1']['values'][a])}%" in html
    flipped = delays.flipped(
        {c["case_id"]: c for c in map(json.loads, (root / "cases/test/cases.jsonl").open())},
        {r["case_id"]: r for r in map(json.loads, (root / "data/labels/labels.jsonl").open())},
    )
    assert len(flipped) == 1
    assert f"{len(flipped)} of {len(CASES)}" in html
    fixed = fixed_rule.analyze(root, root / "runs")
    n = len(CASES)
    assert f'{fixed["consistent"]} of {n}</b>cases answered the same way' in html
    assert f'{fixed["correct"]} of {n}</b>answered correctly' in html
    assert fixed["total"] == n
    changed = sum(
        1
        for cid, ds in fixed["cases"].items()
        for d, r in zip(ds, runs_of(root, cid))
        if d != r
    )
    assert f'<span class="hl">{changed}</span> runs' in html
    assert "the fix changes the result" not in html


def runs_of(root, cid):
    from eval import metrics

    rows = sorted(
        (o for o in metrics.load_outputs(root / "runs/confirm-system") if o["case_id"] == cid),
        key=lambda o: o.get("run", 0),
    )
    from eval import confirm

    return [confirm.mapped(o) for o in rows]


# @criterion C10
def test_each_answer_square_has_its_letter_class_and_the_wrong_mark(tree):
    _, out, _, _ = tree
    one, three, four = [b for b in blocks((out / "index.html").read_text()) if "sq " in b]
    sq = squares(one)
    assert "".join(s[0] for s in sq[:10]) == NAIVE_FIRST
    assert [bool(s[1]) for s in sq[:10]] == [d != "R" for d in NAIVE_FIRST]
    assert "".join(s[0] for s in sq[10:]) == "R" * 10
    assert not any(s[1] for s in sq[10:])  # the code version was right here
    assert f">{NAIVE_FIRST[0]}</div>" in one
    assert 'aria-label="no refund, wrong"' in one
    assert squares(three) == [("R", " miss")] * 10  # the flipped label is no refund
    assert len(squares(four)) == 10 and "still gets a refund" in four
    assert "four times" in one and "six times" in one
    assert "arrived 14 min early" in one and "CID" in one


# @criterion C10
def test_the_statute_quote_is_the_clause_with_each_highlight_marked(tree):
    from html import escape

    root, out, cfg, _ = tree
    text = clause_text(root, cfg["statute_clause"])
    law = re.search(r'<div class="law"><cite>(.*?)</cite>(.*?)</div>', (out / "index.html").read_text())
    assert law.group(1) == escape(cfg["statute_cite"])
    assert re.sub(r"</?mark>", "", law.group(2)) == escape(text + cfg["statute_continuation"])
    adr = (
        ROOT / "docs/decisions/0008-delay-refund-when-the-passenger-did-not-fly.md"
    ).read_text()
    norm = lambda t: re.sub(r"\s+", " ", re.sub("[-\u2013\u2014]+", "--", t))
    assert norm(cfg["statute_continuation"].strip()) in norm(adr)
    assert cfg["statute_highlight"]
    for h in cfg["statute_highlight"]:
        assert h in text + cfg["statute_continuation"]
        assert f"<mark>{escape(h)}</mark>" in law.group(2)


# @criterion C14
def test_evidence_links_resolve_and_the_offer_and_contact_are_present(tree):
    _, out, cfg, _ = tree
    html = (out / "index.html").read_text()
    close = blocks(html)[-1]
    assert cfg["offer"] in close
    assert f'href="{cfg["contact_url"]}"' in close
    assert "mailto:" not in html and "@" not in html
    assert "Hire me on Upwork" in close
    five = blocks(html)[4]
    for c in cfg["costs"]:
        assert c["text"] in five and f'<a href="{c["source_url"]}">{c["source_label"]}</a>' in five
    assert len(cfg["evidence"]) == 6
    for ev in cfg["evidence"]:
        assert f'<a href="{ev["href"]}">{ev["label"]}' in close
        page = (out / ev["href"]).read_text()
        assert 'href="index.html"' in page and ev["label"] in page
    assert not (out / "evidence.html").exists()


def test_fonts_and_licence_are_copied_and_declared(tree):
    _, out, _, _ = tree
    assert (out / "fonts/Archivo-800.woff2").is_file()
    assert (out / "fonts/OFL-Archivo.txt").is_file()
    css = (out / "style.css").read_text()
    assert 'font-family:"Archivo";font-weight:800' in css
    assert "Archivo-700" not in css  # a font that is not there is not declared


def test_size_and_no_other_host(tree):
    _, out, _, _ = tree
    assert (out / "index.html").stat().st_size + (out / "style.css").stat().st_size < 150_000
    for f in out.rglob("*"):
        if f.suffix not in (".html", ".css"):
            continue
        text = f.read_text()
        for tag in re.findall(r"<[^>]+>", text):
            if tag.startswith(("<a ", "<a>")):
                continue
            assert not re.search(r'(?:src|href)="(?:[a-z]+:)?//', tag), (f, tag)
        assert not re.search(r"url\(\s*['\"]?(?:https?:)?//", text), f
        assert "@import" not in text


def test_a_build_without_runs_still_gives_the_close(tmp_path):
    build(
        tmp_path,
        FIX / "report.json",
        CONFIG,
        flights_dir=FIX / "bts",
        chatbots_dir=tmp_path / "none",
    )
    html = (tmp_path / "index.html").read_text()
    assert [b for b in blocks(html) if "need the runs" in b].__len__() == 2
    assert "Is it the right one?" in html and "<b>" not in html.split("With the rule fixed")[1].split("</section>")[0]
    assert len(blocks(html)) == 4


def test_real_story_matches_the_runs(tmp_path):
    runs = Path(os.environ.get("SAY_IT_TWICE_RUNS", ROOT / "runs"))
    root = Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT)
    path = runs / "confirm" / "report.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    build(tmp_path, path, CONFIG, runs, root=root, fonts_dir=ROOT / "vendor/fetched/fonts")
    html = (tmp_path / "index.html").read_text()
    for share in ("84%", "100%", "21 of 130"):
        assert share in html
    fixed = fixed_rule.analyze(root, runs)
    assert f'{fixed["correct"]} of {fixed["total"]}</b>answered correctly' in html
    one = blocks(html)[0]
    assert NAIVE_FIRST in "".join(s[0] for s in squares(one))
    assert not (tmp_path / "evidence.html").exists()
