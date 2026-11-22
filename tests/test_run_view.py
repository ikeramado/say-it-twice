from pathlib import Path

from PIL import Image

from report import run_view

ROOT = Path(__file__).parent / "fixtures" / "run_view"
RUNS = ROOT / "system_run"


def test_tree_steps_in_order_and_decision():
    text = "\n".join(run_view.tree("c1", 0, ROOT, RUNS))
    order = [
        "flight looked up",
        "rule version fetched",
        "policy fetched",
        "triggers checked",
        "engine decision",
        "explanation",
    ]
    pos = [text.index(s) for s in order]
    assert pos == sorted(pos)
    assert "arrival delay 189" in text
    assert "rule version v2, clause DL-2025-10-08-19A-schedule-change" in text
    assert text.rstrip().endswith("@criterion C3")


def test_escalated_shows_trigger_reasons():
    text = "\n".join(run_view.tree("c1", 1, ROOT, RUNS))
    assert "fired: amount_over_threshold" in text


def test_gif_has_many_frames(tmp_path):
    p = tmp_path / "a.gif"
    run_view.write_gif(run_view.tree("c1", 0, ROOT, RUNS), p)
    with Image.open(p) as im:
        assert im.format == "GIF" and im.n_frames > 1


def test_main_exit_codes(capsys):
    assert run_view.main(["--case", "c1", "--run", "0", "--root", str(ROOT), "--runs", str(RUNS)]) == 0
    assert "case c1 run 0" in capsys.readouterr().out
    assert run_view.main(["--case", "nope", "--run", "0", "--root", str(ROOT), "--runs", str(RUNS)]) == 1


def test_case_with_path_separator_refused(capsys):
    for bad in ("../c1", "a/b", "..", "a\\b"):
        args = ["--case", bad, "--run", "0", "--root", str(ROOT), "--runs", str(RUNS)]
        assert run_view.main(args) == 1
