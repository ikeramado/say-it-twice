"""The labels are frozen under tag labels-v1 before any engine exists (T12)."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def test_labels_file_matches_the_prereg_hash():
    raw = (ROOT / "data/labels/labels.jsonl").read_bytes()
    rows = [json.loads(line) for line in raw.decode().splitlines()]
    assert len(rows) == len({r["case_id"] for r in rows}) > 0
    prereg = (ROOT / "docs/modules/prereg.md").read_text()
    m = re.search(r"Labels tag and hash:\*\* labels-v1 ([0-9a-f]{64})", prereg)
    assert m and m.group(1) == hashlib.sha256(raw).hexdigest()


def test_tag_exists_and_no_engine_before_it():
    tag = git("rev-parse", "--verify", "labels-v1^{commit}").strip()
    assert tag
    names = git("log", tag, "--name-only", "--format=").splitlines()
    assert not [n for n in names if Path(n).name == "engine.py"]
    tagged = git("show", f"{tag}:data/labels/labels.jsonl")
    assert hashlib.sha256(tagged.encode()).hexdigest() == hashlib.sha256(
        (ROOT / "data/labels/labels.jsonl").read_bytes()
    ).hexdigest()


# @criterion C4
def test_every_case_labeled_once_with_a_valid_decision():
    ids = []
    for rel in ("cases/dev/cases.jsonl", "cases/test/cases.jsonl"):
        for line in (ROOT / rel).read_text().splitlines():
            if line.strip():
                ids.append(json.loads(line)["case_id"])
    rows = [
        json.loads(line)
        for line in (ROOT / "data/labels/labels.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 315
    labeled = [r["case_id"] for r in rows]
    assert len(set(labeled)) == len(labeled)
    assert sorted(labeled) == sorted(ids)
    assert {r["decision"] for r in rows} <= {"refund", "no_refund", "escalate"}
