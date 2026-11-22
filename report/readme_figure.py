"""The README's image, `docs/ten-answers.svg`: one flight asked ten times, three rows of ten
squares (the plain agent, the same model with the rules in code, the rule fixed), each square
the answer's letter in the colour of the story page.

`python -m report.readme_figure [--root .] [--runs-dir runs] [--case ID] [--out PATH]`. Built
from the confirmatory runs and `eval.fixed_rule`, no model call; the letters (`LETTER`) and the
colours (`--refund`, `--norefund`, `--escalate`, `--ground`, `--text`, `--quiet` of `STYLE`) are
the story page's, imported. It exits 2 with a message when `runs/confirm-naive` or
`runs/confirm-system` is missing, as the site build does. The output is deterministic."""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from eval import fixed_rule
from eval.confirm import mapped
from report.confirm import esc
from report.site import ROOT, STYLE
from report.site.matrix import LETTER, RUNS, WORDS
from report.site.story import flight_code

OUT = "docs/ten-answers.svg"
SQ, GAP, LEFT, TOP = 34, 6, 130, 64
ROWS = (
    "Plain agent",
    "Rules in code",
    "Rule fixed",
)


def color(name):
    """A custom property of the story page's stylesheet, e.g. `refund`."""
    return re.search(rf"--{name}:(#[0-9a-fA-F]{{6}})", STYLE).group(1)


def read_rows(root, runs_dir, case_id):
    """The ten answers of the case for the three rows, as strings of letters; None when the
    plain agent's or the system's confirmatory run is missing."""
    rows = []
    for agent in ("naive", "system"):
        base = Path(runs_dir) / f"confirm-{agent}" / "outputs"
        if not base.is_dir():
            return None
        outs = []
        for n in range(RUNS):
            f = base / f"{case_id}_{n}.json"
            if not f.exists():
                return None
            outs.append(json.loads(f.read_text()))
        rows.append("".join(LETTER[mapped(o)] for o in outs))
    fixed = fixed_rule.analyze(root, runs_dir)["cases"][case_id]
    rows.append("".join(LETTER[d] for d in fixed))
    return rows


def render(flight, rows):
    """The SVG text for the flight's name and the three letter strings."""
    width = LEFT + RUNS * (SQ + GAP) + 20
    height = TOP + len(rows) * (SQ + 22) + 44
    fill = {
        d: color(n) for d, n in (("R", "refund"), ("N", "norefund"), ("E", "escalate"))
    }
    ground, text, quiet = color("ground"), color("text"), color("quiet")
    mono = "ui-monospace,Menlo,Consolas,monospace"
    out = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="Flight {esc(flight)} asked '
            "ten times: the plain agent answers differently each time, the rules in code give one "
            'answer">'
        ),
        f'<rect width="{width}" height="{height}" fill="{ground}"/>',
        (
            f'<text x="20" y="34" fill="{text}" font-family="{mono}" font-size="15" '
            f'font-weight="600">Flight {esc(flight)}, the same question asked ten times</text>'
        ),
    ]
    for r, (label, letters) in enumerate(zip(ROWS, rows)):
        y = TOP + r * (SQ + 22)
        out.append(
            f'<text x="20" y="{y + SQ // 2 + 5}" fill="{quiet}" font-family="{mono}" '
            f'font-size="12">{esc(label)}</text>'
        )
        for i, d in enumerate(letters):
            x = LEFT + i * (SQ + GAP)
            word = next(w for k, w in WORDS.items() if LETTER[k] == d)
            out.append(
                f'<rect x="{x}" y="{y}" width="{SQ}" height="{SQ}" rx="3" fill="{fill[d]}">'
                f"<title>{esc(word)}</title></rect>"
                f'<text x="{x + SQ // 2}" y="{y + SQ // 2 + 5}" text-anchor="middle" '
                f'fill="{ground}" font-family="{mono}" font-size="14" font-weight="600">{d}</text>'
            )
    ky = height - 16
    for i, (d, name) in enumerate(
        (("R", "refund"), ("N", "no refund"), ("E", "hand to a person"))
    ):
        kx = 20 + i * 150
        out.append(
            f'<rect x="{kx}" y="{ky - 10}" width="11" height="11" rx="2" fill="{fill[d]}"/>'
            f'<text x="{kx + 17}" y="{ky}" fill="{quiet}" font-family="{mono}" '
            f'font-size="12">{d} {esc(name)}</text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m report.readme_figure")
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--runs-dir", default=None, help="default: <root>/runs")
    p.add_argument("--case", help="default: the story's first case (config/site.yaml)")
    p.add_argument("--out", default=None, help=f"default: <root>/{OUT}")
    a = p.parse_args(argv)
    root = Path(a.root)
    runs_dir = Path(a.runs_dir) if a.runs_dir else root / "runs"
    case_id = (
        a.case
        or yaml.safe_load((ROOT / "config/site.yaml").read_text())["story"][
            "first_case"
        ]
    )
    try:
        rows = read_rows(root, runs_dir, case_id)
    except (OSError, ValueError, KeyError):
        rows = None
    if rows is None:
        print(
            f"readme_figure: no confirmatory runs of {case_id} in {runs_dir} "
            "(confirm-naive and confirm-system are needed)",
            file=sys.stderr,
        )
        return 2
    cases = [
        json.loads(x)
        for x in (root / "cases/test/cases.jsonl").read_text().splitlines()
        if x.strip()
    ]
    case = next(c for c in cases if c["case_id"] == case_id)
    out = Path(a.out) if a.out else root / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(flight_code(case), rows), encoding="utf-8")
    print(f"readme_figure: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
