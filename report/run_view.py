"""The run view: one case-run of the system agent as a tree of its steps, no model call.

python -m report.run_view --case <case_id> --run <n> [--gif <path>] [--root <dir>]

Reads runs/confirm-system/traces/<case>_<run>.json (a list of call records, the steps are in
the last one), outputs/<case>_<run>.json (decision, explanation) and the flight record from
data/clean/flights (through agents.system.tools). The root is --root, or SAY_IT_TWICE_DATA_ROOT,
or the repository.
"""

import argparse
import json
import sys
import textwrap
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from agents.system import tools

RUN_DIR = "runs/confirm-system"


def _load(case, run, root, runs=None):
    if "/" in case or "\\" in case or ".." in case:
        raise ValueError(f"bad case id: {case!r}")
    base = Path(runs) if runs else Path(tools.data_root(root)) / RUN_DIR
    trace = json.loads((base / "traces" / f"{case}_{run}.json").read_text("utf-8"))
    out = json.loads((base / "outputs" / f"{case}_{run}.json").read_text("utf-8"))
    return trace[-1], out


def _flight_line(call, root):
    carrier, number, day, origin = call["args"]
    head = f"{carrier} {number} {day} {origin}"
    if not call.get("found"):
        return head + ": not found"
    rec = tools.get_flight(carrier, number, day, origin, root)
    if rec is None:
        return head + ": record not in data/clean"
    cancelled = "cancelled" if rec["cancelled"] == "1" else "flown"
    delay = rec["arrival_delay"] or "none"
    return f"{head} -> {rec['destination']}, {cancelled}, arrival delay {delay} min"


def tree(case, run, root=None, runs=None):
    """The tree as a list of lines, in the order the steps happened."""
    t, out = _load(case, run, root, runs)
    calls = {c["tool"]: c for c in t["tool_calls"]}
    lines = [f"case {case} run {run}"]
    steps = []
    if "get_flight" in calls:
        steps.append(("flight looked up", [_flight_line(calls["get_flight"], root)]))
    if "get_rule" in calls:
        steps.append(("rule version fetched", [str(calls["get_rule"]["result"])]))
    pol = calls.get("get_policy") or calls.get("purchase_candidates")
    if pol:
        steps.append(("policy fetched", [str(pol["result"])]))
    trig = t.get("triggers") or []
    steps.append(
        ("triggers checked", [f"fired: {r}" for r in trig] or ["none fired"])
    )
    eng = t.get("engine") or {}
    steps.append(
        (
            "engine decision",
            [
                f"{out['decision']} (engine: {eng.get('decision')})",
                f"rule version {out.get('rule_version')}, clause {out.get('clause')}",
            ],
        )
    )
    steps.append(("explanation", [out["explanation"]]))
    for i, (name, kids) in enumerate(steps):
        last = i == len(steps) - 1
        lines.append(("`-- " if last else "|-- ") + name)
        pad = "    " if last else "|   "
        for k in kids:
            wrapped = textwrap.wrap(k, 88, replace_whitespace=True) or [""]
            lines.append(pad + "`-- " + wrapped[0])
            lines.extend(pad + "    " + w for w in wrapped[1:])
    return lines


def write_gif(lines, path, hold=600):
    """An animated GIF of the tree drawing itself, one line more per frame."""
    font = ImageFont.load_default()
    w = max(int(font.getlength(x)) for x in lines) + 20
    h = 16 * len(lines) + 20
    frames = []
    for n in range(1, len(lines) + 1):
        im = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(im)
        for i, x in enumerate(lines[:n]):
            d.text((10, 10 + 16 * i), x, fill="black", font=font)
        frames.append(im)
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=[400] * (len(frames) - 1) + [hold * 3],
        loop=0,
    )


def main(argv=None):
    ap = argparse.ArgumentParser(prog="report.run_view")
    ap.add_argument("--case", required=True)
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--gif")
    ap.add_argument("--root")
    ap.add_argument("--runs", help="the run directory, default <root>/runs/confirm-system")
    a = ap.parse_args(argv)
    try:
        lines = tree(a.case, a.run, a.root, a.runs)
    except (FileNotFoundError, ValueError) as e:
        print(f"report.run_view: {e}", file=sys.stderr)
        return 1
    for x in lines:
        print(x)
        if sys.stdout.isatty():
            sys.stdout.flush()
            time.sleep(0.3)
    if a.gif:
        write_gif(lines, a.gif)
    return 0


if __name__ == "__main__":
    sys.exit(main())
