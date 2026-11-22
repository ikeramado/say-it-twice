"""The README and the LICENSE (card T65): the headings and figures it states, its links, the
commands of Reproduce, the image `docs/ten-answers.svg` and the words it must not hold. The
`real` tests need the confirmatory runs: SAY_IT_TWICE_RUNS=<repo>/runs and
SAY_IT_TWICE_DATA_ROOT=<repo>."""

import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from eval import delays, failures, fixed_rule
from eval.confirm import mapped
from report import readme_figure
from report.site.matrix import LETTER
from tests.test_confirm_report import build
from tests.test_fixed_rule import CASES, LABEL, REGISTERED, RUNS, TRACES

REPO = Path(__file__).resolve().parent.parent
README = (REPO / "README.md").read_text(encoding="utf-8")
FETCHED = REPO / "vendor/fetched/PolyForm-Noncommercial-1.0.0.md"
FIXTURE = Path(__file__).parent / "fixtures" / "readme"
HEADINGS = [
    "Where the AI works and where it does not",
    "The result",
    "How it was measured",
    "Where it fails",
    "Scope",
    "Reproduce",
    "Repository",
]
NOTICE = "Required Notice: Copyright (c) 2026 Iker Amado"


def tracked_or_staged():
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.split("\0")

    return set(git("ls-files", "-z")) | set(
        git("diff", "--cached", "--name-only", "-z")
    )


def section(title):
    return README.split(f"\n## {title}\n")[1].split("\n## ")[0]


def whole(token, text):
    return re.search(rf"(?<![\w.,%]){re.escape(token)}(?![\w%])", text) is not None


# --- the text ------------------------------------------------------------------


def test_headings_in_order_and_the_top_holds_the_figures():
    heads = re.findall(r"^## (.+)$", README, flags=re.MULTILINE)
    assert [h for h in heads if h in HEADINGS] == HEADINGS
    top = README.split("\n## ")[0]
    for s in ("![", "docs/ten-answers.svg", "84%", "100%", "of 130"):
        assert s in top
    assert "](https://ikeramado.github.io/say-it-twice/)" in top
    assert "<details><summary>Technical details</summary>" in README
    assert README.index("<details>") > README.index("## Repository")
    for s in ("21 of 130", "103 of 130", "DL 1832", "2 cases", "20 runs"):
        assert s in README


def test_relative_links_and_images_point_to_tracked_or_staged_files():
    files = tracked_or_staged()
    targets = re.findall(r"!?\[[^\]]*\]\(([^)\s]+)\)", README)
    targets += re.findall(r'(?:src|href)="([^"]+)"', README)
    assert targets
    for t in targets:
        if re.match(r"[a-z]+:|#", t):
            continue
        assert t.split("#")[0] in files, t


def test_reproduce_commands_exist():
    code = "\n".join(
        re.findall(r"```\n(.*?)```", section("Reproduce"), flags=re.DOTALL)
    )
    targets = set(
        re.findall(
            r"^([a-z][\w-]*):", (REPO / "Makefile").read_text(), flags=re.MULTILINE
        )
    )
    made = re.findall(r"\bmake ([\w-]+)", code)
    mods = re.findall(r"python -m ([\w.]+)", code)
    assert made and mods
    for t in made:
        assert t in targets, t
    for m in mods:
        assert importlib.util.find_spec(m) is not None, m


def test_every_percentage_and_n_of_130_is_in_the_results():
    results = "\n".join(
        p.read_text() for p in sorted((REPO / "docs/results").glob("*.md"))
    )
    tokens = re.findall(r"\b\d+(?:\.\d+)?%", README) + re.findall(
        r"\b\d+ of 130(?![\d,])", README
    )
    assert tokens
    for t in set(tokens):
        assert whole(t, results), t


def test_banned_words_emoji_and_the_required_sentences():
    licence = (REPO / "LICENSE").read_text(encoding="utf-8")
    for name, text in (("README", README), ("LICENSE", licence)):
        for s in ("tasks/", ("STATE" + ".md"), ("FRICTIONS" + ".md"), "AGENTS.md", ("." + "harness")):
            assert s not in text, (name, s)
        assert "harness" not in text.lower(), name
        for ch in text:
            assert not (0x1F300 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF), (
                name,
                ch,
            )
    for w in ("study", "hypothesis", "preregistration"):
        assert w not in README.lower(), w
    assert "No agent was deployed with real users." in README
    for sentence in README.split("."):
        if "never invents" in sentence:
            assert re.search(r"\d", sentence), sentence


def test_the_licence_is_the_fetched_text_with_the_required_notice():
    licence = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert licence.startswith("# PolyForm Noncommercial License 1.0.0")
    lines = licence.rstrip("\n").splitlines()
    assert lines[-1] == NOTICE
    fetched = FETCHED.read_text(encoding="utf-8")
    assert "\n".join(lines[:-1]).rstrip("\n") == fetched.rstrip("\n")


# --- the image -----------------------------------------------------------------


@pytest.fixture
def root(tmp_path):
    decisions = {
        a: {c: [d] * RUNS for c, d in REGISTERED.items()}
        for a in ("naive", "cheap_strong", "system")
    }
    for a in decisions.values():
        a["dot-p1"] = ["no_refund"] * RUNS
    decisions["naive"]["d1"] = ["refund", "no_refund"] * 5
    build(tmp_path, CASES, LABEL, decisions)
    tdir = tmp_path / "runs/confirm-system/traces"
    tdir.mkdir()
    for cid, line in TRACES.items():
        for i in range(RUNS):
            (tdir / f"{cid}_{i}.json").write_text(json.dumps([line]))
    return tmp_path


def squares(svg):
    return re.findall(r">([RNE])</text>", svg)


def test_the_figure_is_built_from_runs_and_is_the_same_twice(root):
    a, b = root / "a.svg", root / "b.svg"
    for out in (a, b):
        rc = readme_figure.main(
            [
                "--root",
                str(root),
                "--runs-dir",
                str(root / "runs"),
                "--case",
                "d1",
                "--out",
                str(out),
            ]
        )
        assert rc == 0
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes() == (FIXTURE / "ten-answers.svg").read_bytes()
    s = squares(a.read_text())
    assert ["".join(s[i : i + 10]) for i in (0, 10, 20)] == [
        "RNRNRNRNRN",
        "R" * 10,
        "N" * 10,
    ]


def test_the_figure_exits_2_without_runs(root, capsys):
    rc = readme_figure.main(
        ["--root", str(root), "--runs-dir", str(root / "nowhere"), "--case", "d1"]
    )
    assert rc == 2
    assert "confirm-naive" in capsys.readouterr().err
    assert not (root / "docs/ten-answers.svg").exists()


# --- the real runs ---------------------------------------------------------------

RUNS_DIR, DATA_ROOT = (
    os.environ.get("SAY_IT_TWICE_RUNS"),
    os.environ.get("SAY_IT_TWICE_DATA_ROOT"),
)
needs_runs = pytest.mark.skipif(
    not (RUNS_DIR and DATA_ROOT and (Path(RUNS_DIR) / "confirm-system").is_dir()),
    reason="SAY_IT_TWICE_RUNS and SAY_IT_TWICE_DATA_ROOT point at no confirmatory runs",
)


def figure_rows():
    """{key: value} of docs/results/readme-figures.md."""
    text = (REPO / "docs/results/readme-figures.md").read_text()
    return dict(re.findall(r"^\| `(\w+)` \| ([^|]+?) \|", text, flags=re.MULTILINE))


@needs_runs
def test_real_figure_rows():

    case = "test-ren-002"
    rows = readme_figure.read_rows(DATA_ROOT, RUNS_DIR, case)
    assert [len(r) for r in rows] == [10, 10, 10]
    assert rows[0] == "RNNRNRNNNR"
    for agent, row in (("system", rows[1]),):
        outs = [
            json.loads(
                (
                    Path(RUNS_DIR) / f"confirm-{agent}/outputs/{case}_{n}.json"
                ).read_text()
            )
            for n in range(10)
        ]
        assert row == "".join(LETTER[mapped(o)] for o in outs)
    assert rows[2] == "".join(
        LETTER[d] for d in fixed_rule.analyze(DATA_ROOT, RUNS_DIR)["cases"][case]
    )
    svg = (REPO / "docs/ten-answers.svg").read_text()
    assert ["".join(squares(svg)[i : i + 10]) for i in (0, 10, 20)] == rows


@needs_runs
def test_real_figures_match():

    report = json.loads((Path(RUNS_DIR) / "confirm/report.json").read_text())
    h1 = report["primary"]["H1"]["values"]
    fixed = fixed_rule.analyze(DATA_ROOT, RUNS_DIR)
    cases, labels, _, _ = failures.load(DATA_ROOT, RUNS_DIR)
    system = {
        cid: [
            json.loads(
                (Path(RUNS_DIR) / f"confirm-system/outputs/{cid}_{n}.json").read_text()
            )
            for n in range(10)
        ]
        for cid in fixed["cases"]
    }

    changed = {
        cid: sum(d != mapped(o) for d, o in zip(ds, system[cid]))
        for cid, ds in fixed["cases"].items()
    }
    want = {
        "plain_same": f"{round(100 * h1['naive'])}%",
        "plain_same_cases": f"{round(h1['naive'] * fixed['total'])} of {fixed['total']}",
        "code_same": f"{round(100 * h1['system'])}%",
        "wrong_rule": f"{len(delays.flipped(cases, labels))} of {fixed['total']}",
        "correct_fixed": f"{fixed['correct']} of {fixed['total']}",
        "handed_over": f"{sum(all(d == 'escalate' for d in ds) for ds in fixed['cases'].values())}"
        f" of {fixed['total']}",
        "lacked_fact": f"{sum(1 for n in changed.values() if n)} cases",
        "lacked_fact_runs": f"{sum(changed.values())} runs",
    }
    assert figure_rows() == want
    for key, text in want.items():
        assert key == "plain_same_cases" or text in README, key
