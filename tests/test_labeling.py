import ast
import csv
import json
import re
from pathlib import Path

import pytest

from labeling import kit

REPO = Path(__file__).resolve().parent.parent
HIDDEN = ("bts_flight", "clean_case_id", "constructed", "meta", "type", "attack",
          "contradicts_facts", "carrier_month", "other_policy_version")


def _case(i: int, typ: str = "delay_above", **facts) -> dict:
    f = {"cancelled": {"value": False, "constructed": False},
         "arrival_delay_min": {"value": 200, "constructed": False},
         "purchase_date": {"value": "2024-05-01", "constructed": True}}
    f.update({k: {"value": v, "constructed": True} for k, v in facts.items()})
    return {"case_id": f"dev-x-{i:03d}", "carrier": "DL", "flight_number": "100",
            "flight_date": "2024-06-10", "origin": "ATL", "facts": f,
            "message": {"text": f"Message {i}.", "constructed": True},
            "type": typ, "bts_flight": {"carrier": "DL"}, "clean_case_id": "dev-x-999",
            "meta": {"rule_version": "v1", "policy_version": "DL-2024-03-12",
                     "carrier_month": "DL:2024-06"}}


def _tree(tmp_path: Path, cases: list[dict]) -> Path:
    for i, rel in enumerate(kit.CASE_FILES):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        part = cases if i == 0 else []
        p.write_text("".join(json.dumps(c) + "\n" for c in part))
    dot = tmp_path / "cases" / "test" / "dot"
    dot.mkdir(parents=True)
    (dot / "cases.jsonl").write_text(json.dumps(_case(900)) + "\n")
    return tmp_path


def _answers(root: Path, who: str, rows) -> None:
    p = kit.work(root) / who / "answers.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(kit.FIELDS)
        w.writerows(rows)


def _row(cid, decision="refund"):
    return [cid, decision, "v1-42305-refund", "v1", "DL-2024-03-12"]


def test_sheets_show_case_and_texts_only(tmp_path):
    # @criterion C4
    cases = [_case(1), _case(2, typ="missing_fact")]
    del cases[1]["facts"]["purchase_date"]
    root = _tree(tmp_path, cases)
    _answers(root, "sonnet", [_row("dev-x-001", "no_refund")])
    sheets = kit.label_sheets(root, "opus")
    files = sorted(p.name for p in sheets.iterdir())
    o1, o2 = kit.opaque_id("dev-x-001"), kit.opaque_id("dev-x-002")
    assert files == sorted([f"{o1}.md", f"{o2}.md"])  # never cases/test/dot/
    s1 = (sheets / f"{o1}.md").read_text()
    for want in (o1, "DL", "100", "2024-06-10", "2024-05-01", "Message 1.",
                 "arrival_delay_min", "`v1`", "v1-42305-refund", "`DL-2024-03-12`",
                 "DL-2024-03-12-19A"):
        assert want in s1, want
    for word in HIDDEN:
        assert word not in s1, word
    assert "no_refund" not in s1.split("## Your answer")[0]
    s2 = (sheets / f"{o2}.md").read_text()
    assert "Purchase date: not given" in s2 and "DL-2023-06-22" in s2
    assert "missing_fact" not in s2
    with pytest.raises(kit.LabelingError):
        kit.label_sheets(root, "gpt")


def test_sheets_module_reads_no_agents_or_eval():
    # @criterion C4
    for path in (REPO / "labeling").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                assert n.split(".")[0] not in ("agents", "eval"), (path, n)


def test_import_reports_missing(tmp_path):
    # @criterion C4
    root = _tree(tmp_path, [_case(i) for i in range(1, 4)])
    _answers(root, "opus", [_row("dev-x-001"), _row("dev-x-002", "maybe")])
    r = kit.import_answers(root, "opus")
    assert r["missing"] == ["dev-x-003"] and r["invalid"] == ["dev-x-002"]


def _three(tmp_path, ncases=10, opus=None, sonnet=None, rules=None):
    root = _tree(tmp_path, [_case(i) for i in range(1, ncases + 1)])
    base = ["refund"] * (ncases // 2) + ["no_refund"] * (ncases - ncases // 2)
    for who, d in (("opus", opus), ("sonnet", sonnet), ("rules", rules)):
        d = d or base
        _answers(root, who, [_row(f"dev-x-{i + 1:03d}", x) for i, x in enumerate(d)])
    return root


def _ten(tmp_path):
    opus = ["refund"] * 5 + ["no_refund"] * 5
    sonnet = list(opus)
    sonnet[0] = "no_refund"
    sonnet[9] = "refund"
    return _three(tmp_path, opus=opus, sonnet=sonnet)


def test_kappa_and_disagreements(tmp_path):
    # @criterion C4
    root = _ten(tmp_path)
    r = kit.compare(root)
    # opus-sonnet: po = 0.8, pe = 0.5, kappa = 0.6; rules equals opus
    assert r["kappas"]["opus-sonnet"] == pytest.approx(0.6)
    assert r["kappas"]["opus-rules"] == pytest.approx(1.0)
    assert r["kappas"]["sonnet-rules"] == pytest.approx(0.6)
    assert r["three_way"] == pytest.approx(0.8)
    assert r["disagreements"] == ["dev-x-001", "dev-x-010"]
    assert "dev-x-010" in r["path"].read_text()


def _write_res(root, rows):
    with (kit.work(root) / "resolutions.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(list(kit.FIELDS) + ["reason", "reviewed"])
        w.writerows(rows)


def test_three_way_carries_agreeing_resolutions(tmp_path):
    # @criterion C4
    # cases 1-3 agreed by all three; 4, 5, 6 are not
    opus = ["refund", "refund", "no_refund", "refund", "refund", "no_refund"]
    sonnet = ["refund", "refund", "no_refund", "no_refund", "no_refund", "refund"]
    rules = ["refund", "refund", "no_refund", "refund", "no_refund", "escalate"]
    root = _three(tmp_path, 6, opus, sonnet, rules)
    _write_res(root, [
        ["dev-x-004", "refund", "r-clause", "v2", "DL-x", "human read it", ""],  # rules agrees
        ["dev-x-005", "refund", "r-clause", "v2", "DL-x", "human read it", ""],  # rules does not
    ])
    r = kit.compare(root)
    assert r["disagreements"] == ["dev-x-005", "dev-x-006"]
    assert list(r["carried"]) == ["dev-x-004"]
    rows = list(csv.DictReader(r["path"].open()))
    assert [x["case_id"] for x in rows] == ["dev-x-005", "dev-x-006"]
    assert rows[0]["resolution_decision"] == "refund" and rows[1]["resolution_decision"] == ""
    assert rows[0]["rules_decision"] == "no_refund"
    # the human sees case 5 again: reviewed, then the case freezes with the resolution
    with pytest.raises(kit.LabelingError, match="unresolved"):
        kit.label_freeze(root)
    _write_res(root, [
        ["dev-x-004", "refund", "r-clause", "v2", "DL-x", "human read it", ""],
        ["dev-x-005", "refund", "r-clause", "v2", "DL-x", "human read it", "yes"],
        ["dev-x-006", "exclude", "", "", "", "texts do not settle it", "yes"],
    ])
    kit.label_freeze(root)
    labels = {x["case_id"]: x for x in map(
        json.loads, (root / "data/labels/labels.jsonl").read_text().splitlines())}
    assert len(labels) == 5 and "dev-x-006" not in labels
    assert labels["dev-x-004"]["clause"] == "r-clause"  # the carried resolution's row
    assert labels["dev-x-001"]["clause"] == "v1-42305-refund"  # an agreed row


def test_exclude_resolution_is_never_carried(tmp_path):
    # @criterion C4
    root = _three(tmp_path, 2, ["refund", "refund"], ["refund", "refund"],
                  ["refund", "no_refund"])
    _write_res(root, [["dev-x-002", "exclude", "", "", "", "unclear", ""]])
    r = kit.compare(root)
    assert r["disagreements"] == ["dev-x-002"] and not r["carried"]


def test_freeze_three_needs_no_audit(tmp_path):
    # @criterion C4
    root = _three(tmp_path, 4)
    r = kit.label_freeze(root)
    assert r["labels"] == 4 and not r["excluded"]
    labels = [json.loads(x) for x in (root / "data/labels/labels.jsonl").read_text().splitlines()]
    assert all(set(x) == set(kit.FIELDS) for x in labels)
    assert not (kit.work(root) / "audit-sample.txt").exists()


def test_freeze_refuses_then_writes(tmp_path):
    # @criterion C4
    root = _ten(tmp_path)
    with pytest.raises(kit.LabelingError, match="unresolved"):
        kit.label_freeze(root)
    assert not (root / "data" / "labels" / "labels.jsonl").exists()
    _write_res(root, [
        ["dev-x-001", "refund", "v1-42305-refund", "v1", "DL-2024-03-12", "rule text", "yes"],
        ["dev-x-010", "exclude", "", "", "", "the texts do not settle it", "yes"],
    ])
    r = kit.label_freeze(root)
    labels = [json.loads(x) for x in (root / "data/labels/labels.jsonl").read_text().splitlines()]
    assert len(labels) == 9 and r["labels"] == 9
    assert {x["case_id"] for x in labels} == {f"dev-x-{i:03d}" for i in range(1, 10)}
    assert labels[0]["decision"] == "refund"
    excl = (root / "labeling" / "excluded.md").read_text()
    assert "dev-x-010" in excl and "the texts do not settle it" in excl


@pytest.mark.parametrize("flight_date,own", [("2026-01-10", "v3-fr-pause-renumbered"),
                                             ("2026-08-10", "v4-fr-pause-extension")])
def test_sheets_resolve_follows(flight_date, own):
    # @criterion C4
    c = _case(1, renumbered=True)
    c["flight_date"] = flight_date
    s = kit.sheet_text(c)
    assert own in s and "Inherited from version `v2`" in s
    assert "v2-260.2-cancelled" in s and "v2-260.2-delay" in s


ID_PATTERN = re.compile(r"\b(dev|test)-[a-z]{3}-\d{3}")


def test_sheets_use_opaque_ids(tmp_path):
    # @criterion C4
    cases = [_case(i) for i in range(1, 6)]
    cases[0]["case_id"] = "dev-mis-003"
    cases[1]["case_id"] = "test-ren-002"
    root = _tree(tmp_path, cases)
    sheets = kit.label_sheets(root, "opus")
    real = {c["case_id"] for c in cases}
    rows = (kit.work(root) / "opus" / "answers.csv").read_text().splitlines()[1:]
    for p in sheets.iterdir():
        text = p.read_text()
        assert not ID_PATTERN.search(p.name) and not ID_PATTERN.search(text)
        assert not any(r in text for r in real)
    assert not any(ID_PATTERN.search(r) for r in rows)
    ids = [r.split(",")[0] for r in rows]
    assert ids == sorted(ids) == sorted(kit.opaque_id(c) for c in real)
    assert sorted(p.stem for p in sheets.iterdir()) == ids
    mapping = json.loads((kit.work(root) / "map.json").read_text())
    assert mapping == {kit.opaque_id(c): c for c in real}
    assert not list((kit.work(root) / "opus").glob("map*"))


def test_import_maps_opaque_ids_back(tmp_path):
    # @criterion C4
    root = _tree(tmp_path, [_case(i) for i in range(1, 4)])
    kit.label_sheets(root, "opus")
    _answers(root, "opus", [_row(kit.opaque_id(f"dev-x-{i:03d}")) for i in (1, 2)])
    r = kit.import_answers(root, "opus")
    assert r["missing"] == ["dev-x-003"] and not r["unknown"]
    got = kit.read_answers(kit.work(root) / "opus" / "answers.csv", root)
    assert sorted(got) == ["dev-x-001", "dev-x-002"]
    assert got["dev-x-001"]["case_id"] == "dev-x-001"
