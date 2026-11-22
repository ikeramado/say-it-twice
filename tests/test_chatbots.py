"""eval.chatbots (card T54): validate, propose, totals on a fixture; the protocol's flights."""

import csv
import json
import os
from datetime import date
from pathlib import Path

import pytest
import yaml

from agents.system import engine, tools
from eval import chatbots, metrics
from rules import lookup

FIXTURE = Path(__file__).parent / "fixtures/chatbots/questions.yaml"
DAY = "2026-11-21"
ROOT = Path(__file__).resolve().parent.parent


def make(tmp_path, day=DAY, text="You get a ticket refund."):
    proto = chatbots.load(FIXTURE)
    for c, q, r in chatbots.expected(proto):
        d = tmp_path / day
        d.mkdir(exist_ok=True)
        (d / f"{chatbots.stem(c, q, r)}.txt").write_text(text)
    return proto


# @criterion C10
def test_complete_folder_exits_0(tmp_path, capsys):
    make(tmp_path)
    argv = ["validate", "--questions", str(FIXTURE), "--dir", str(tmp_path)]
    assert chatbots.main(argv) == 0
    assert capsys.readouterr().out == ""


# @criterion C10
def test_missing_and_empty_answer_exit_1(tmp_path, capsys):
    make(tmp_path)
    (tmp_path / DAY / "alpha-q1-1.txt").unlink()
    (tmp_path / DAY / "beta-q2-2.txt").write_text("  \n")
    argv = ["validate", "--questions", str(FIXTURE), "--dir", str(tmp_path)]
    assert chatbots.main(argv) == 1
    out = capsys.readouterr().out.splitlines()
    assert "alpha-q1-1: missing answer" in out
    assert f"{DAY}/beta-q2-2.txt: empty answer" in out
    assert len(out) == 2


# @criterion C10
def test_off_protocol_date_exits_1(tmp_path, capsys):
    make(tmp_path, day="2026-11-19")
    argv = ["validate", "--questions", str(FIXTURE), "--dir", str(tmp_path)]
    assert chatbots.main(argv) == 1
    assert any("off-protocol day" in line for line in capsys.readouterr().out.splitlines())


# @criterion C10
def test_stray_file_and_png_are_not_answers(tmp_path):
    proto = make(tmp_path)
    (tmp_path / DAY / "notes.txt").write_text("x")
    (tmp_path / DAY / "alpha-q1-1.png").write_bytes(b"png")
    gaps = chatbots.validate(proto, tmp_path)
    assert gaps == [
        f"{DAY}/alpha-q1-1.png: not an answer of the protocol",
        f"{DAY}/notes.txt: not an answer of the protocol",
    ]


# @criterion C10
def test_answers_split_over_two_days_count_once(tmp_path, capsys):
    proto = make(tmp_path)
    other = tmp_path / "2026-11-22"
    other.mkdir()
    (tmp_path / DAY / "beta-q2-2.txt").rename(other / "beta-q2-2.txt")
    assert chatbots.validate(proto, tmp_path) == []
    found, gaps = chatbots.find(tmp_path, proto)
    assert gaps == [] and found[("beta", "q2", 2)] == ["2026-11-22"]
    assert len(found) == 8
    got = {t["chatbot"]: t for t in chatbots.totals(proto, tmp_path)}
    assert (got["beta"]["asked"], got["beta"]["dates"]) == (4, [DAY, "2026-11-22"])


# @criterion C10
def test_same_answer_on_two_days_is_a_gap(tmp_path):
    proto = make(tmp_path)
    other = tmp_path / "2026-11-22"
    other.mkdir()
    (other / "alpha-q1-1.txt").write_text("again")
    assert chatbots.validate(proto, tmp_path) == [
        f"alpha-q1-1: answered on several days: {DAY}, 2026-11-22"
    ]


# @criterion C10
def test_invented_proposed_by_phrase_match_and_totals_follow_human(tmp_path):
    proto = make(tmp_path, text="You are owed a ticket refund and compensation.")
    rows = chatbots.propose(proto, tmp_path)
    assert len(rows) == 8
    assert {r["invented_proposed"] for r in rows} == {"compensation"}
    ent = yaml.safe_load(metrics.ENTITLEMENTS.read_text())
    assert chatbots.proposed({"rule_version": "v2"}, "a ticket refund", ent) == []
    # the human fills the sheet: overrides one proposal, rules on the decisions
    sheet = chatbots.read_sheet(tmp_path)
    for r in sheet:
        r["decision"] = "right" if r["chatbot"] == "alpha" else "wrong"
        r["invented_human"] = "yes"
    sheet[0]["invented_human"] = "no"
    sheet[7]["decision"] = "none"
    with (tmp_path / "scores.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=chatbots.COLUMNS)
        w.writeheader()
        w.writerows(sheet)
    assert chatbots.validate(proto, tmp_path) == []
    # propose again keeps the human's columns
    again = chatbots.propose(proto, tmp_path)
    assert again[0]["invented_human"] == "no"
    got = {t["chatbot"]: t for t in chatbots.totals(proto, tmp_path)}
    assert got["alpha"] == {
        "chatbot": "alpha",
        "asked": 4,
        "right": 4,
        "wrong": 0,
        "none": 0,
        "invented": 3,
        "dates": [DAY],
    }
    assert (got["beta"]["wrong"], got["beta"]["none"], got["beta"]["invented"]) == (
        3,
        1,
        4,
    )


def test_unfilled_sheet_is_a_gap(tmp_path):
    proto = make(tmp_path)
    chatbots.propose(proto, tmp_path)
    gaps = chatbots.validate(proto, tmp_path)
    assert gaps and all(g.startswith("scores.csv") for g in gaps)


def test_totals_prints_json(tmp_path, capsys):
    make(tmp_path)
    argv = ["totals", "--questions", str(FIXTURE), "--dir", str(tmp_path)]
    assert chatbots.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert [t["chatbot"] for t in out] == ["alpha", "beta"]
    assert set(out[0]) == {
        "chatbot",
        "asked",
        "right",
        "wrong",
        "none",
        "invented",
        "dates",
    }


def test_protocol_shape():
    proto = chatbots.load()
    assert proto["chatbots"] == ["chatgpt", "gemini", "meta-ai"]
    assert len(proto["questions"]) == 4 and proto["repeats"] == 1
    assert len(chatbots.expected(proto)) == 12
    assert "days" not in proto and proto["not_before"] == "2026-11-20"
    q4 = proto["questions"][3]
    assert q4["facts"]["travelled"] is True
    assert q4["expected_decision"] == "no_refund"
    assert q4["decided_by_clause"] == "v1-42305-refund"


def _data_root():
    return tools.data_root(os.environ.get(tools.ENV))


@pytest.mark.parametrize("q", chatbots.load()["questions"], ids=lambda q: q["id"])
def test_question_names_a_real_flight_and_its_rule(q):
    root = _data_root()
    month = root / f"data/clean/flights/{q['date'][:7]}.csv"
    if not month.is_file():
        pytest.skip(
            f"clean month absent: {month} (set {tools.ENV} to a checkout with data/)"
        )
    rec = tools.get_flight(
        q["carrier"], q["flight_number"], q["date"], q["origin"], root
    )
    assert rec is not None, "no such BTS flight"
    assert rec["destination"] == q["destination"]
    assert (rec["cancelled"] == "1") == q["facts"]["cancelled"]
    if not q["facts"]["cancelled"]:
        assert int(rec["arrival_delay"]) == q["facts"]["arrival_delay_min"]
    d = date.fromisoformat(q["date"])
    rule = lookup.rule_for(d, False)
    assert rule.id == q["rule_version"]
    pd = date.fromisoformat(q["facts"]["purchase_date"])
    pol = tools.get_policy(q["carrier"], pd)
    assert pol.id == q["policy_version"]
    facts = {k: v for k, v in q["facts"].items() if k != "travelled"}
    got = engine.decide(facts, rule, pol)
    if q["id"] == "q4":
        # ADR-0008: the passenger flew, so no refund; the engine reads no `travelled` fact
        # and still says refund for a 3 hour delay. Only q4 differs from the engine.
        assert got["decision"] == "refund"
        assert q["expected_decision"] == "no_refund"
        assert q["facts"]["travelled"] is True
        assert q["decided_by_clause"] == "v1-42305-refund"
    else:
        assert got["decision"] == q["expected_decision"]
    ent = yaml.safe_load(metrics.ENTITLEMENTS.read_text())
    allowed = set(ent["rule_versions"][q["rule_version"]])
    allowed |= set(ent["policy_versions"].get(q["policy_version"], []))
    assert q["not_given"] == [p for p in ent["vocabulary"] if p not in allowed]
