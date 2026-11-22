"""The escalation tray (T51) on a fixture of system traces."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from report import tray

FIX = Path(__file__).parent / "fixtures" / "tray"


@pytest.fixture
def root(tmp_path):
    import shutil

    shutil.copytree(FIX / "data", tmp_path / "runs")
    return tmp_path


def lines(root):
    p = root / tray.LOG
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


# @criterion C5
def test_queue_only_escalated(root):
    assert {(i["case_id"], i["run"]) for i in tray.queue(root)} == {
        ("c-refund", 0), ("c-refund", 1), ("c-norefund", 0), ("c-oos", 1), ("c-noflight", 0)}


# @criterion C5
def test_actions_append_one_line_each(root):
    calls = [("approve", "c-refund", 0, {"note": "ok"}),
             ("change", "c-oos", 1, {"to": "no_refund", "note": "why"}),
             ("reject", "c-norefund", 0, {})]
    for n, (action, case, run, kw) in enumerate(calls, 1):
        tray.act(root, action, case, run, **kw)
        assert len(lines(root)) == n
    ls = lines(root)
    for line, (action, case, run, _) in zip(ls, calls, strict=True):
        assert (line["case"], line["run"], line["action"]) == (case, run, action)
    assert set(ls[0]) == {"time", "case", "run", "action", "before", "after", "note"}
    assert (ls[0]["before"], ls[0]["after"]) == ("escalate", "refund")
    assert (ls[1]["before"], ls[1]["after"], ls[1]["note"]) == ("escalate", "no_refund", "why")
    assert ls[2]["after"] == "rejected"


# @criterion C5
def test_before_is_current_decision(root):
    tray.act(root, "approve", "c-refund", 0)
    tray.act(root, "change", "c-refund", 0, to="no_refund")
    tray.act(root, "change", "c-refund", 1, to="refund")
    ls = lines(root)
    assert ls[1]["before"] == ls[0]["after"] == "refund"
    assert ls[2]["before"] == "escalate"


# @criterion C5
def test_refusals_write_nothing(root):
    for args in [("approve", "nope", 0), ("approve", "c-refund", 9),
                 ("approve", "c-noflight", 0), ("approve", "c-oos", 1)]:
        with pytest.raises(tray.TrayError):
            tray.act(root, *args)
    with pytest.raises(tray.TrayError):
        tray.act(root, "change", "c-refund", 0, to="maybe")
    assert lines(root) == []


# @criterion C5
def test_preview_without_engine_decision(root):
    it = tray.find(root, "c-noflight", 0)
    assert it["proposal"] is None
    assert tray.preview(it)["decision"] is None
    assert tray.preview(tray.find(root, "c-refund", 0))["decision"] == "refund"


# @criterion C5
def test_static_view_lists_every_case_run(root, tmp_path):
    out = tray.view(root, tmp_path / "site")
    text = out.read_text()
    assert out.name == "tray.html"
    assert text.count("c-refund (run") == 2
    for cid in ("c-refund", "c-norefund", "c-oos", "c-noflight"):
        assert cid in text
    assert "c-done" not in text and "http" not in text


# @criterion C5
def test_cli(root):
    r = subprocess.run([sys.executable, "-m", "report.tray", "--root", str(root),
                        "approve", "c-noflight", "0"], check=False, capture_output=True, text=True)
    assert r.returncode == 2 and lines(root) == []


REAL = Path(__file__).parents[1]
DATA = Path(__import__("os").environ.get("SAY_IT_TWICE_DATA_ROOT", "/home/iker/say-it-twice"))


@pytest.mark.skipif(not (DATA / "runs/confirm-system").exists(), reason="no confirmatory run")
def test_real_run_count(tmp_path):
    import re

    expected = json.loads((DATA / "runs/confirm/report.json").read_text())
    n = expected["cost_view"]["agents"]["system"]["escalations"]
    text = tray.view(DATA, tmp_path).read_text()
    head, _, dot = text.partition("DOT external case, reported apart")
    assert len(re.findall(r"<section>", head)) == n == 100
    assert len(re.findall(r"<section>", dot)) == 10


def run_cli(root, *args):
    return subprocess.run([sys.executable, "-m", "report.tray", "--root", str(root), *args],
                          check=False, capture_output=True, text=True)


# @criterion C5
def test_cli_list_show_view_approve(root, tmp_path):
    r = run_cli(root, "list")
    assert r.returncode == 0 and "c-oos 1" in r.stdout and "c-done" not in r.stdout
    r = run_cli(root, "show", "c-refund", "0")
    assert r.returncode == 0 and json.loads(r.stdout)["preview"]["decision"] == "refund"
    r = run_cli(root, "view", "--out", str(tmp_path / "v"))
    assert r.returncode == 0 and (tmp_path / "v" / "tray.html").exists()
    r = run_cli(root, "approve", "c-refund", "0", "--note", "n")
    assert r.returncode == 0 and len(lines(root)) == 1
