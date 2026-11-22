"""Popular chatbots asked by hand (ADR-0006, card T54): validate the saved answers, propose the
invented flags, total the human's scores. Nothing here calls any chatbot.

`python -m eval.chatbots validate|propose|totals [--questions docs/chatbots/questions.yaml]
[--dir data/chatbots]`

Answers are `<dir>/<YYYY-MM-DD>/<chatbot>-<question>-<repeat>.txt` (text only, in one or
several dated folders); the sheet is
`<dir>/scores.csv` with columns chatbot, question, repeat, date, decision (right, wrong, none),
invented_proposed, invented_human (yes or no), note. `validate` exits 1 on any gap, one line per
gap. `propose` fills `invented_proposed` with `eval.failures.invented_phrases` (the phrases
stated that the rule version does not list) and never touches the human's columns. `totals`
prints a JSON list, one object per chatbot, from the human's columns only.
"""

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

from eval import failures, metrics

QUESTIONS = Path(__file__).resolve().parent.parent / "docs/chatbots/questions.yaml"
DIR = Path("data/chatbots")
COLUMNS = (
    "chatbot",
    "question",
    "repeat",
    "date",
    "decision",
    "invented_proposed",
    "invented_human",
    "note",
)
DECISIONS = ("right", "wrong", "none")
FLAGS = ("yes", "no")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}$")


def load(path=QUESTIONS):
    return yaml.safe_load(Path(path).read_text())


def expected(proto):
    """Every (chatbot, question id, repeat) the protocol asks."""
    return [
        (c, q["id"], r)
        for c in proto["chatbots"]
        for q in proto["questions"]
        for r in range(1, proto["repeats"] + 1)
    ]


def stem(c, q, r):
    return f"{c}-{q}-{r}"


def day_folders(root):
    root = Path(root)
    return sorted(d for d in root.iterdir() if d.is_dir()) if root.is_dir() else []


def valid_day(name, proto):
    try:
        return date.fromisoformat(name) >= date.fromisoformat(proto["not_before"])
    except ValueError:
        return False


def find(root, proto):
    """({(chatbot, question, repeat): [day folder names with its .txt]}, [gap lines])."""
    gaps, found = [], {}
    folders = day_folders(root)
    for d in folders:
        if not DAY.match(d.name):
            gaps.append(f"{d.name}: not a date folder")
        elif not valid_day(d.name, proto):
            gaps.append(f"{d.name}: off-protocol day (before {proto['not_before']})")
    days = [d for d in folders if DAY.match(d.name)]
    names = {stem(*k): k for k in expected(proto)}
    for d in days:
        for f in sorted(d.iterdir()):
            k = names.get(f.stem)
            if k is None or f.suffix != ".txt":
                gaps.append(f"{d.name}/{f.name}: not an answer of the protocol")
            elif f.suffix == ".txt":
                found.setdefault(k, []).append(d.name)
    return found, gaps


def validate(proto, root):
    found, gaps = find(root, proto)
    for k in expected(proto):
        name = stem(*k)
        days = found.get(k, [])
        if not days:
            gaps.append(f"{name}: missing answer")
            continue
        if len(days) > 1:
            gaps.append(f"{name}: answered on several days: {', '.join(days)}")
        d = Path(root) / days[0]
        if not (d / f"{name}.txt").read_text().strip():
            gaps.append(f"{days[0]}/{name}.txt: empty answer")
    gaps += sheet_gaps(proto, root)
    return gaps


def read_sheet(root):
    path = Path(root) / "scores.csv"
    if not path.is_file():
        return None
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def sheet_gaps(proto, root):
    sheet = read_sheet(root)
    if sheet is None:
        return []
    gaps, keys = [], set(expected(proto))
    seen = set()
    for row in sheet:
        try:
            k = (row["chatbot"], row["question"], int(row["repeat"]))
        except (KeyError, ValueError, TypeError):
            gaps.append(f"scores.csv: unreadable row {row}")
            continue
        name = stem(*k)
        if k not in keys:
            gaps.append(f"scores.csv: {name}: not a question of the protocol")
        if k in seen:
            gaps.append(f"scores.csv: {name}: twice")
        seen.add(k)
        if row.get("decision") not in DECISIONS:
            gaps.append(f"scores.csv: {name}: decision must be one of {DECISIONS}")
        if row.get("invented_human") not in FLAGS:
            gaps.append(f"scores.csv: {name}: invented_human must be yes or no")
    for k in expected(proto):
        if k not in seen:
            gaps.append(f"scores.csv: {stem(*k)}: no row")
    return gaps


def proposed(question, text, ent):
    """The entitlement phrases the answer states that the question's rule version does not list."""
    label = {"rule_version": question["rule_version"], "policy_version": None}
    return failures.invented_phrases({"explanation": text}, label, ent)


def propose(proto, root):
    """Add a row per saved answer, set `invented_proposed`; the human's columns stay as they are."""
    ent = yaml.safe_load(metrics.ENTITLEMENTS.read_text())
    qs = {q["id"]: q for q in proto["questions"]}
    old = {
        (r["chatbot"], r["question"], int(r["repeat"])): r
        for r in read_sheet(root) or []
    }
    found, _ = find(root, proto)
    rows = []
    for k in expected(proto):
        if k not in found:
            if k in old:
                rows.append(old[k])
            continue
        c, q, r = k
        text = (Path(root) / found[k][0] / f"{stem(*k)}.txt").read_text()
        row = {col: "" for col in COLUMNS} | old.get(k, {})
        row.update(
            chatbot=c,
            question=q,
            repeat=r,
            date=found[k][0],
            invented_proposed=";".join(proposed(qs[q], text, ent)),
        )
        rows.append(row)
    path = Path(root) / "scores.csv"
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)
    return rows


def totals(proto, root):
    found, _ = find(root, proto)
    sheet = {
        (r["chatbot"], r["question"], int(r["repeat"])): r
        for r in read_sheet(root) or []
    }
    out = []
    for c in proto["chatbots"]:
        mine = [k for k in expected(proto) if k[0] == c]
        rows = [sheet[k] for k in mine if k in sheet]
        out.append(
            {
                "chatbot": c,
                "asked": sum(1 for k in mine if k in found),
                "right": sum(r["decision"] == "right" for r in rows),
                "wrong": sum(r["decision"] == "wrong" for r in rows),
                "none": sum(r["decision"] == "none" for r in rows),
                "invented": sum(r["invented_human"] == "yes" for r in rows),
                "dates": sorted({d for k in mine for d in found.get(k, [])}),
            }
        )
    return out


def main(argv=None):
    p = argparse.ArgumentParser(prog="eval.chatbots")
    p.add_argument("command", choices=("validate", "propose", "totals"))
    p.add_argument("--questions", default=str(QUESTIONS))
    p.add_argument("--dir", default=str(DIR))
    a = p.parse_args(argv)
    proto = load(a.questions)
    if a.command == "validate":
        gaps = validate(proto, a.dir)
        for g in gaps:
            print(g)
        return 1 if gaps else 0
    if a.command == "propose":
        rows = propose(proto, a.dir)
        print(f"{len(rows)} rows in {Path(a.dir) / 'scores.csv'}")
        return 0
    print(json.dumps(totals(proto, a.dir), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
