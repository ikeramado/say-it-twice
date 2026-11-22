"""eval/failures.py on a small fixture whose counts are computed by hand (card T42)."""

import json

import pytest
import yaml

from eval import failures

VERSIONS = {
    "versions": [
        {"id": "v1", "first_day": "2024-05-16", "last_day": "2024-10-27"},
        {"id": "v2", "first_day": "2024-10-28", "last_day": None},
    ]
}


def case(cid, carrier, ctype, flight_date):
    return {
        "case_id": cid,
        "carrier": carrier,
        "type": ctype,
        "flight_date": flight_date,
        "facts": {},
        "meta": {"carrier_month": f"{carrier}:{flight_date[:7]}"},
    }


CASES = [
    case("t-a", "AA", "delay_above", "2024-06-01"),
    case("t-b", "DL", "out_of_scope", "2024-06-02"),
    case("t-c", "DL", "boundary", "2024-11-01"),
    case("t-d", "AA", "renumbered", "2024-06-03"),  # no label: left out
]

LABELS = [
    {
        "case_id": "t-a",
        "decision": "refund",
        "clause": "v1-a",
        "rule_version": "v1",
        "policy_version": "none",
    },
    {
        "case_id": "t-b",
        "decision": "escalate",
        "clause": "out_of_scope",
        "rule_version": "v1",
        "policy_version": "none",
    },
    {
        "case_id": "t-c",
        "decision": "no_refund",
        "clause": "v2-c",
        "rule_version": "v2",
        "policy_version": "none",
    },
]


def out(cid, run, decision, explanation="", rule_version=None, **kw):
    return {
        "case_id": cid,
        "run": run,
        "decision": decision,
        "explanation": explanation,
        "clause": f"{cid}-clause",
        "rule_version": rule_version,
        **kw,
    }


NAIVE = [
    out("t-a", 0, "no_refund", "No refund under v1.", "v1"),  # wrong
    out("t-a", 1, "refund", "", "v1"),  # correct
    out(
        "t-b", 0, "refund", "We give a voucher.", "v1-42305-refund"
    ),  # missed, clause id, voucher
    out("t-b", 1, "escalate"),  # needed
    out(
        "t-c", 0, "refund", "Under v1 you get compensation.", "v1"
    ),  # wrong, version, invented
    out(
        "t-c", 1, "refund", "", "v2", parse_error=True
    ),  # mapped to escalate: unnecessary
    out("t-d", 0, "no_refund"),  # unlabeled
]
CHEAP = [out("t-a", 0, "escalate"), out("t-b", 0, "escalate")]
SYSTEM = [
    out("t-a", 0, "refund", "You get a full refund.", "v1"),  # v1 lists full refund
    out("t-b", 0, "no_refund", "", "v1"),  # missed
    out("t-b", 1, "no_refund", "", "v1"),  # missed
    out("t-c", 0, "no_refund", "No voucher is due.", "v2"),  # invented voucher
]
TRACE = [
    {
        "engine": {"decision": "no_refund", "clause": "DL-x"},
        "rule_version": "v1",
        "policy_versions": ["DL-1"],
    }
]


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


@pytest.fixture
def root(tmp_path):
    jsonl(tmp_path / "cases/test/cases.jsonl", CASES)
    jsonl(tmp_path / "data/labels/labels.jsonl", LABELS)
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules/versions.yaml").write_text(yaml.safe_dump(VERSIONS))
    for agent, rows in (("naive", NAIVE), ("cheap_strong", CHEAP), ("system", SYSTEM)):
        d = tmp_path / "runs" / f"confirm-{agent}" / "outputs"
        d.mkdir(parents=True)
        for o in rows:
            (d / f"{o['case_id']}_{o['run']}.json").write_text(json.dumps(o))
    t = tmp_path / "runs/confirm-system/traces"
    t.mkdir()
    (t / "t-b_0.json").write_text(json.dumps(TRACE))
    doc = tmp_path / failures.DOC
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# F\n\nHand-written prose.\n\n"
        + "".join(
            f"<!-- generated:{n} -->\nold\n<!-- /generated:{n} -->\n\n"
            for n in (
                "totals",
                "system_cases",
                "by_type",
                "by_airline",
                "flags",
                "examples",
                "system_invented",
                "sensitivity",
            )
        )
    )
    return tmp_path


def test_counts_equal_the_hand_computed_ones(root):
    data = failures.analyze(root, root / "runs")
    n = data["naive"]
    assert (n["runs"], n["critical"], n["wrong"], n["missed"], n["invented_runs"]) == (
        6,
        3,
        2,
        1,
        2,
    )
    assert n["by_type"]["delay_above"] == {
        "runs": 2,
        "wrong": 1,
        "missed": 0,
        "critical": 1,
    }
    assert n["by_type"]["out_of_scope"] == {
        "runs": 2,
        "wrong": 0,
        "missed": 1,
        "critical": 1,
    }
    assert n["by_type"]["boundary"] == {
        "runs": 2,
        "wrong": 1,
        "missed": 0,
        "critical": 1,
    }
    assert "renumbered" not in n["by_type"]
    assert n["by_airline"]["AA"] == {"runs": 2, "wrong": 1, "missed": 0, "critical": 1}
    assert n["by_airline"]["DL"] == {"runs": 4, "wrong": 1, "missed": 1, "critical": 2}
    assert n["flags"] == {
        "critical": 3,
        "version_error": 2,
        "clause_id_only": 1,
        "invented": 2,
        "either": 2,
    }
    assert [r["case"]["case_id"] for r in n["examples"]] == ["t-a", "t-b", "t-c"]
    assert n["phrases"] == {"compensation": 1, "voucher": 1}
    assert data["cheap_strong"]["critical"] == 0
    s = data["system"]
    assert (s["critical"], s["missed"], s["invented_runs"]) == (2, 2, 1)
    assert s["phrases"] == {"voucher": 1}
    assert [c["case_id"] for c in s["cases"]] == ["t-b"]
    c = s["cases"][0]
    assert (c["critical"], c["runs"], c["engine_decision"], c["engine_clause"]) == (
        2,
        2,
        "no_refund",
        "DL-x",
    )
    assert (c["label_decision"], c["policy_versions"]) == ("escalate", ["DL-1"])


def test_writes_between_markers_and_check_finds_a_change(root, capsys):
    args = ["--root", str(root), "--runs-dir", str(root / "runs")]
    doc = root / failures.DOC
    assert failures.main(args + ["--check"]) == 1
    assert failures.main(args) == 0
    text = doc.read_text()
    assert "Hand-written prose." in text and "\nold\n" not in text
    assert "| naive | 6 | 2 | 1 | 3 | 2 |" in text
    assert failures.main(args + ["--check"]) == 0
    doc.write_text(
        text.replace("| naive | 6 | 2 | 1 | 3 | 2 |", "| naive | 6 | 2 | 1 | 4 | 2 |")
    )
    assert failures.main(args + ["--check"]) == 1


def test_a_missing_marker_fails(root):
    doc = root / failures.DOC
    doc.write_text(doc.read_text().replace("<!-- generated:flags -->", ""))
    assert failures.main(["--root", str(root), "--runs-dir", str(root / "runs")]) == 1


def test_h2_recomputes_with_one_label_overridden(root):
    cases, labels, table, ent = failures.load(root, root / "runs")

    def rs(agent):
        outs = [
            json.loads(p.read_text())
            for p in sorted(
                (root / "runs" / f"confirm-{agent}" / "outputs").glob("*.json")
            )
        ]
        return failures.rows(outs, cases, labels, table, ent)

    naive = rs("naive")
    assert {
        k: failures.h2(naive)[k] for k in ("runs", "critical", "wrong", "missed")
    } == {"runs": 6, "critical": 3, "wrong": 2, "missed": 1}
    # t-b read as refund: run 0 (refund) turns correct, run 1 (escalate) unnecessary
    got = failures.h2(naive, {"t-b": "refund"})
    assert (got["critical"], got["wrong"], got["missed"]) == (2, 2, 0)
    assert got["critical_per_100"] == pytest.approx(100 * 2 / 6)
    assert got["missed_per_100"] == 0
    system = failures.h2(rs("system"), {"t-b": "no_refund"})
    assert (system["critical"], system["critical_per_100"]) == (0, 0)
    assert failures.h2(rs("system"))["critical"] == 2  # the frozen label is untouched
    assert labels["t-b"]["decision"] == "escalate"
