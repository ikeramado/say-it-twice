import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from cases import split
from cases.builder import TARGETS
from tests.test_cases import synth_pools

ROOT = Path(__file__).resolve().parent.parent


def test_split_by_carrier_month_with_exact_counts():
    # @criterion C6
    res = split.build_split(synth_pools())
    dev_cm = {c["meta"]["carrier_month"] for c in res["dev"]}
    test_cm = {c["meta"]["carrier_month"] for c in res["test"]}
    assert not dev_cm & test_cm
    assert dev_cm <= set(res["dev_carrier_months"])
    assert test_cm <= set(res["test_carrier_months"])
    for i, side in enumerate(("dev", "test")):
        for t, want in TARGETS.items():
            assert sum(c["type"] == t for c in res[side]) == want[i], (side, t)
    assert len(res["dev"]) == 185 and len(res["test"]) == 130


def test_shortfall_escalates():
    # @criterion C6
    few = synth_pools(["2024-01", "2024-02"])
    with pytest.raises(split.Shortfall):
        split.build_split(few)


def test_outputs_hash_and_prereg(tmp_path):
    # @criterion C6
    res = split.build_split(synth_pools())
    prereg = tmp_path / "prereg.md"
    shutil.copy(ROOT / "docs/modules/prereg.md", prereg)
    out = tmp_path / "cases"
    (out / "test" / "dot").mkdir(parents=True)
    (out / "test" / "dot" / "keep.txt").write_text("T10")
    digest = split.write_outputs(res, out=out, prereg=prereg, last_month="2026-08")
    assert (out / "test" / "dot" / "keep.txt").exists()
    lines = (out / "test" / "cases.jsonl").read_text().splitlines()
    assert len(lines) == 130 and len(json.loads(lines[0])) > 5
    canon = sorted(
        json.dumps(
            json.loads(x), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        for x in lines
    )
    assert (
        digest == hashlib.sha256("".join(x + "\n" for x in canon).encode()).hexdigest()
    )
    assert (out / "test" / "hash.txt").read_text().strip() == digest
    assert len((out / "dev" / "cases.jsonl").read_text().splitlines()) == 185
    text = prereg.read_text()
    assert "Sampling seed:** 20261118" in text and f"Test case hash:** {digest}" in text
    assert "TODO: last month" not in text and "last month used: 2026-08" in text
    split.update_prereg(prereg, 20261118, digest, "2026-08")  # idempotent
    assert prereg.read_text() == text


def test_committed_files_agree_with_prereg():
    # @criterion C6
    text = (ROOT / "docs/modules/prereg.md").read_text()
    assert "Sampling seed:** 20261118" in text and "TODO: last month" not in text
    m = re.search(r"Test case hash:\*\* ([0-9a-f]{64})", text)
    assert m
    cases = [
        json.loads(x)
        for x in (ROOT / "cases/test/cases.jsonl").read_text().splitlines()
    ]
    assert split.test_hash(cases) == m.group(1)
