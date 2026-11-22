"""Screen 1's chatbot block and the protocol page (T55)."""

import re
import subprocess
from pathlib import Path

import pytest

from eval import chatbots as cb
from report.site import ROOT, build
from report.site.chatbots import build_chatbots

FIX = Path(__file__).parent / "fixtures" / "site"
CHAT = FIX / "chatbots"
CONFIG = ROOT / "config" / "site.yaml"
LABEL = "exploratory, small sample, not part of the registered study"


def build_html(tmp_path, chatbots_dir=CHAT):
    build(
        tmp_path / "site",
        FIX / "report.json",
        CONFIG,
        flights_dir=FIX / "bts",
        chatbots_dir=chatbots_dir,
    )
    return (tmp_path / "site" / "method.html").read_text()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("cb")
    return d, build_html(d)


def block(html):
    return html.split('<div class="chatbots" id="chatbots">')[1].split("</section>")[0]


def row(html, chatbot):
    return re.search(rf"<tr><td>{chatbot}</td>(.*?)</tr>", block(html)).group(1)


def test_counts_per_chatbot_match_totals_command(built):
    _, html = built
    by = {t["chatbot"]: t for t in cb.totals(cb.load(), CHAT)}
    assert by["chatgpt"]["asked"] == 2 and by["chatgpt"]["invented"] == 1
    assert row(html, "chatgpt") == ("<td>1 of 2</td><td>1 of 2</td><td>2026-11-20</td>")
    assert row(html, "gemini") == "<td>0 of 1</td><td>1 of 1</td><td>2026-11-20</td>"
    assert row(html, "meta-ai") == (
        "<td>0 of 2</td><td>0 of 2</td><td>2026-11-20, 2026-11-21</td>"
    )


def test_label_link_and_no_image(built):
    d, html = built
    assert LABEL in block(html)
    assert html.count('id="chatbots"') == 1  # T60 links to #chatbots
    assert 'href="chatbots/protocol.html"' in block(html)
    assert "<img" not in html
    page = (d / "site" / "chatbots" / "protocol.html").read_text()
    assert "<pre" in page
    assert "Protocol" in page or "protocol" in page


def test_one_quote_per_chatbot_by_the_rule(built):
    _, html = built
    b = block(html)
    assert b.count("<blockquote") == 3
    # chatgpt: first answer q1 is not invented; the quote is q2, the first marked invented
    assert "chatgpt, q2, asked 2026-11-20 (marked invented)" in b
    assert "Plain answer one." not in b
    # no invented answer: the first by date then question id (q2 on 11-20 before q1 on 11-21)
    assert "meta-ai, q2, asked 2026-11-20 (its first answer)" in b
    assert "Meta later." not in b
    assert "gemini, q1, asked 2026-11-20 (its first answer)" in b


def test_quote_is_whole_escaped_and_keeps_line_breaks(built):
    _, html = built
    b = block(html)
    assert (
        'style="white-space: pre-wrap">You are owed a &lt;b&gt;voucher&lt;/b&gt; '
        "&amp; more.\nSecond line.\n</blockquote>"
    ) in b
    assert "<b>voucher" not in b


def test_no_answers_shows_no_block_and_no_protocol_page(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert build_chatbots(empty) is None
    html = build_html(tmp_path, empty)
    assert 'class="chatbots"' not in html
    assert not (tmp_path / "site" / "chatbots" / "protocol.html").exists()


def test_answer_days_are_not_before_the_protocol_was_committed():
    out = subprocess.run(
        [
            "git",
            "log",
            "--diff-filter=A",
            "--format=%cs",
            "--",
            "docs/chatbots/protocol.md",
        ],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert out, "no git history for docs/chatbots/protocol.md"
    first = min(out)
    days = sorted(
        p.name for p in (ROOT / "data/chatbots").glob("????-??-??") if p.is_dir()
    )
    assert days, "data/chatbots holds no dated folder"
    assert days[0] >= first, f"{days[0]} is dated before the protocol ({first})"
