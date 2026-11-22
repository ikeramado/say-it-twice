import json
import os
import re
from pathlib import Path

import pytest
import yaml

from report.confirm import esc, fmt
from report.site import NAMES, ROOT, build, dig

FIX = Path(__file__).parent / "fixtures" / "site" / "report.json"
CONFIG = ROOT / "config" / "site.yaml"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    build(out, FIX, CONFIG)
    return out


def check_fears(fears, cfg, rep):
    """Every metric row of every fear holds its label and the naive and system numbers."""
    rows = re.findall(r"<tr>.*?</tr>", fears)
    for f in cfg["fears"]:
        assert sum(esc(f["fear"]) in r for r in rows) == 1
        for m in f["metrics"]:
            row = next(r for r in rows if esc(m["label"]) in r)
            for a in ("naive", "system"):
                val = dig(rep, m["path"].format(agent=a))
                assert f"<td>{fmt(val, m['kind'])}</td>" in row
            if m.get("gap"):
                g = dig(rep, m["path"].format(agent="system")) - dig(
                    rep, m["path"].format(agent="naive")
                )
                assert fmt(g, "diff_pct") in row


PAGES = ("audit.html", "cases.html", "versions.html", "break.html", "fails.html", "method.html")


def page(site):
    """The evidence pages of `site`, one after the other (the old long page's screens)."""
    return "".join((site / f).read_text() for f in PAGES if (site / f).exists())


# @criterion C10
def test_first_screen_has_moffatt_headline_and_cost(site):
    html = page(site)
    first = html.split('<section id="s7"')[0]
    rep = json.loads(FIX.read_text())
    assert "Moffatt v. Air Canada (2024 BCCRT 149)" in first
    for h, k, dk in (("H1", "pct", "diff_pct"), ("H2", "num", "diff")):
        p = rep["primary"][h]
        assert fmt(p["values"]["system"], k) in first
        for c in p["comparisons"]:
            row = next(
                r
                for r in re.findall(r"<tr>.*?</tr>", first)
                if f"system vs {NAMES[c['other']]}" in r
                and f"{fmt(c['low'], dk)}," in r
            )
            assert fmt(p["values"][c["other"]], k) in row
            assert f"[{fmt(c['low'], dk)}, {fmt(c['high'], dk)}]" in row
    for other in ("naive", "cheap_strong"):
        row = next(
            r
            for r in re.findall(r"<tr>.*?</tr>", first)
            if f"Dollars per correct decision, system vs {NAMES[other]}" in r
        )
        for a in ("system", other):
            assert fmt(rep["secondary"][a]["cost_per_correct_decision"], "usd") in row
    assert html.index("Moffatt") < html.index("In your business")


# @criterion C14
def test_close_screen_has_contact_link_from_config(site):
    cfg = yaml.safe_load(CONFIG.read_text())
    close = page(site).split('<section id="s8"')[1].split("</section>")[0]
    assert "Does your agent give the same answer twice?" in close
    assert f'href="{cfg["contact_url"]}"' in close
    assert cfg["audit"]["text"] in close


def test_fears_limitations_and_reading_levels(site):
    html = page(site)
    cfg = yaml.safe_load(CONFIG.read_text())
    fears = html.split('<section id="fears"')[1].split("</section>")[0]
    assert len(cfg["fears"]) == 7
    check_fears(fears, cfg, json.loads(FIX.read_text()))
    assert "Limitations against" not in fears and "consent" in fears
    lim = html.split('<section id="limitations"')[1].split("</section>")[0]
    assert "not legal advice" in lim and "transportation.gov/airconsumer/refunds" in lim
    assert "constructed" in lim
    for sid in ("s1", "s7", "s8"):
        sec = html.split(f'<section id="{sid}"')[1].split("</section>")[0]
        assert "for your team" not in sec
    for sid in ("fears", "limitations"):
        sec = html.split(f'<section id="{sid}"')[1].split("</section>")[0]
        assert "for your team" in sec


def test_nothing_points_to_another_host(site):
    for f in (p for p in site.rglob("*") if p.suffix in (".html", ".css")):
        text = f.read_text()
        for tag in re.findall(r"<[^>]+>", text):
            if tag.startswith(("<a ", "<a>")):
                continue  # outbound links to sources and the contact
            assert not re.search(r'(?:src|href)="(?:[a-z]+:)?//?[^"]*"', tag) or (
                'href="/' not in tag and "//" not in tag and "http" not in tag
            )
        assert "@import" not in text and "url(http" not in text


def test_phone_width(site):
    html = page(site)
    assert 'name="viewport" content="width=device-width' in html
    css = (site / "style.css").read_text()
    widths = [int(w) for w in re.findall(r"(?<![-\w])width:\s*(\d+)px", css + html)]
    assert all(w <= 360 for w in widths)


def test_site_numbers_match_real_report(tmp_path):
    runs = Path(os.environ.get("SAY_IT_TWICE_RUNS", ROOT / "runs"))
    path = runs / "confirm" / "report.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    build(tmp_path, path, CONFIG)
    html = page(tmp_path)
    rep = json.loads(path.read_text())
    for h, k, dk in (("H1", "pct", "diff_pct"), ("H2", "num", "diff")):
        p = rep["primary"][h]
        for a in ("system", "naive", "cheap_strong"):
            assert fmt(p["values"][a], k) in html
        for c in p["comparisons"]:
            assert f"[{fmt(c['low'], dk)}, {fmt(c['high'], dk)}]" in html
    assert fmt(rep["secondary"]["system"]["cost_per_correct_decision"], "usd") in html
    fears = html.split('<section id="fears"')[1].split("</section>")[0]
    check_fears(fears, yaml.safe_load(CONFIG.read_text()), rep)


# @criterion C10
def test_limitations_block_states_the_delay_reading_without_a_runs_dir(site):
    lim = page(site).split('<section id="limitations"')[1].split("</section>")[0]
    assert "did not fly" in lim
    assert "ADR-0008" in lim
    assert (
        "per 100 runs" not in lim
    )  # the figures need the runs: see tests/test_delays.py


def screen_one(html):
    """The delay-reading section (it was part of screen one, now on the fails page)."""
    return html.split('<section id="delays"')[1].split("</section>")[0]


# @criterion C10
def test_screen_one_shows_the_corrected_reading_beside_the_registered(tmp_path, site):
    from eval import delays
    from report.site import screen_delays, screen_headline
    from tests.test_confirm_report import build as build_tree
    from tests.test_delays import CASES, DECISIONS, LABEL

    root = build_tree(tmp_path, CASES, LABEL, DECISIONS)
    data = delays.analyze(root, root / "runs")
    cfg = yaml.safe_load(CONFIG.read_text())
    cfg["_delays"] = data
    rep = json.loads(FIX.read_text())
    one = screen_delays(rep, cfg)
    reg = f"<td>{fmt(rep['primary']['H2']['values']['system'], 'num')}</td>"
    assert reg in screen_headline(rep, cfg)
    corr = one.split("Corrected reading of the delay rule (ADR-0008)")[1]
    h2 = data["h2"]["flipped"]
    assert (
        f"<td>{fmt(data['agents']['system']['flipped']['critical_per_100'], 'num')}</td>"
        in corr
    )
    for x in h2["comparisons"]:
        assert (
            f"{fmt(x['difference'], 'diff')} [{fmt(x['low'], 'diff')}, {fmt(x['high'], 'diff')}]"
            in corr
        )
    assert esc(h2["verdict"]) in corr and "not confirmed" in corr
    assert "only when the rule is written right" in one
    assert 'href="method.html#chatbots"' in one
    assert "H1 and H3: unchanged under the corrected reading" in one
    # built with no runs: the block is omitted, with its note
    bare = page(site)
    bare = screen_one(bare)
    assert "Corrected reading of the delay rule" not in bare
    assert "corrected figures need the runs" in bare
    assert 'href="method.html#chatbots"' in bare


def test_real_report_corrected_figures_equal_the_analysis(tmp_path):
    from eval import delays

    runs = Path(os.environ.get("SAY_IT_TWICE_RUNS", ROOT / "runs"))
    path = runs / "confirm" / "report.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    root = Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT)
    build(tmp_path, path, CONFIG, runs, root=root)
    one = screen_one(page(tmp_path))
    data = delays.analyze(root, runs)
    h2 = data["h2"]["flipped"]
    assert fmt(data["agents"]["system"]["flipped"]["critical_per_100"], "num") in one
    for x in h2["comparisons"]:
        assert f"[{fmt(x['low'], 'diff')}, {fmt(x['high'], 'diff')}]" in one
