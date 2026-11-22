"""The six evidence pages (T62): built, linked from the story and back, in the story's look,
no broken link, a trace fragment for every cell, the audit page with and without the report."""

import re
from pathlib import Path

import pytest
import yaml

from report.site import ROOT, build
from report.site.matrix import AGENTS, RUNS
from tests.test_site_matrix import CASES, run_build, write_tree

FIX = Path(__file__).parent / "fixtures" / "site"
CONFIG = ROOT / "config" / "site.yaml"
EVIDENCE = yaml.safe_load(CONFIG.read_text())["evidence"]
PAGES = [e["href"] for e in EVIDENCE]


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    t = tmp_path_factory.mktemp("ev")
    _, fl = write_tree(t)
    return t, run_build(t, fl).site


@pytest.fixture(scope="module")
def bare(tmp_path_factory):
    out = tmp_path_factory.mktemp("bare")
    build(out, FIX / "report.json", CONFIG, flights_dir=FIX / "bts")
    return out


def links(path):
    text = path.read_text()
    return re.findall(r'(?:href|src)="([^"]+)"', text)


def ids(path):
    return set(re.findall(r'\bid="([^"]+)"', path.read_text()))


# @criterion C10
def test_every_page_is_built_linked_from_the_story_and_back_in_its_look(tree):
    _, site = tree
    assert len(PAGES) == 6
    index = (site / "index.html").read_text()
    for ev in EVIDENCE:
        page = (site / ev["href"]).read_text()
        assert f'<a href="{ev["href"]}">{ev["label"]}' in index
        assert 'href="index.html"' in page
        assert '<link rel="stylesheet" href="style.css">' in page
        assert f"<h1 class=\"left\">{ev['label']}</h1>" in page
        assert "<style>" not in page.split("</head>")[0]
    assert (site / "chatbots/protocol.html").is_file()
    assert 'href="../method.html"' in (site / "chatbots/protocol.html").read_text()
    assert 'href="chatbots/protocol.html"' in (site / "method.html").read_text()
    assert len(list(site.glob("*.css"))) == 1


# @criterion C10
def test_no_link_inside_the_site_is_broken(tree, bare):
    for site in (tree[1], bare):
        for f in site.rglob("*.html"):
            if "traces" in f.parts:
                continue
            for href in links(f):
                if re.match(r"(?:[a-z]+:)?//|mailto:", href) or href.startswith("data:"):
                    continue
                path, _, frag = href.partition("#")
                target = (f.parent / path) if path else f
                assert target.is_file(), (f.name, href)
                if frag:
                    assert frag in ids(target), (f.name, href)


# @criterion C10
def test_a_trace_file_exists_for_every_cell_the_matrix_shows(tree):
    _, site = tree
    cases = (site / "cases.html").read_text()
    cells = re.findall(r'<td class="d-\w+"><a href="(traces/[^"]+)"', cases)
    assert len(cells) == len(AGENTS) * len(CASES) * RUNS
    for href in cells:
        frag = (site / href).read_text()
        assert frag.startswith("<h3>") and "<html" not in frag
    for a in AGENTS:
        for cid in CASES:
            for n in range(RUNS):
                assert f'<div class="trace" id="trace-{a}-{cid}-{n}">' in cases
    assert cases.count("<script>") == 1 and "fetch(" in cases
    for f in site.glob("*.html"):
        if f.name != "cases.html":
            assert "<script" not in f.read_text()


def test_the_audit_page_without_the_report_says_it_needs_the_runs(tree, bare):
    _, site = tree  # runs/ here has no confirm/report.html
    for s in (site, bare):
        page = (s / "audit.html").read_text()
        assert "needs the runs" in page and 'href="report.html"' not in page
        assert not (s / "report.html").exists()
        assert 'src="run-view.gif"' in page and (s / "run-view.gif").is_file()


def test_the_audit_page_links_the_report_when_the_runs_have_it(tmp_path):
    _, fl = write_tree(tmp_path)
    (tmp_path / "runs/confirm").mkdir(parents=True)
    (tmp_path / "runs/confirm/report.html").write_text("<html>the report</html>")
    site = run_build(tmp_path, fl).site
    page = (site / "audit.html").read_text()
    assert 'href="report.html"' in page and "needs the runs" not in page
    assert (site / "report.html").read_text() == "<html>the report</html>"


def test_pages_are_small_and_the_old_long_page_is_gone(tree, bare):
    for site in (tree[1], bare):
        assert not (site / "evidence.html").exists()
        for f in site.rglob("*.html"):
            if "traces" not in f.parts:
                assert f.stat().st_size < 2_000_000, f


def test_real_pages_are_under_the_size_limit(tmp_path):
    import os

    runs = Path(os.environ.get("SAY_IT_TWICE_RUNS", ROOT / "runs"))
    root = Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT)
    if not (runs / "confirm/report.json").exists():
        pytest.skip(f"{runs}/confirm/report.json not found")
    build(tmp_path, runs / "confirm/report.json", CONFIG, runs, root=root)
    pages = [f for f in tmp_path.rglob("*.html") if "traces" not in f.parts]
    assert {f.name for f in pages} >= set(PAGES)
    assert all(f.stat().st_size < 2_000_000 for f in pages)
    assert not (tmp_path / "evidence.html").exists()
    assert len(list((tmp_path / "traces/system").glob("*.html"))) == 130 * RUNS
