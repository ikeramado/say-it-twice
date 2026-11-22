import json
import shutil
from pathlib import Path

from cases import dot

ROOT = Path(__file__).resolve().parent.parent


def test_usable_example_becomes_cited_case_and_unusable_is_listed(tmp_path):
    # @criterion C6
    page = tmp_path / f"{dot.GUIDE}.html"
    page.write_text(
        "<p>Intro.</p><p>For example, DL 123 from ATL on March 5, 2024 was cancelled, "
        "so the consumer is entitled to a refund.</p>"
        "<p>For example, a delayed flight, e.g. a long one.</p>"
    )
    cases, answers, unusable = dot.build(tmp_path)
    assert len(cases) == 1 and len(answers) == 1 and len(unusable) == 1
    c = cases[0]
    assert c["source"] == "dot" and c["bts_flight"] is None
    assert c["flight_date"] == "2024-03-05" and c["carrier"] == "DL"
    assert c["citation"] == {
        "file": f"rules/sources/dot/{dot.GUIDE}.html",
        "paragraph": 2,
    }
    assert all(f["from"] == "dot" for f in c["facts"].values())
    assert "answer" not in c and answers[0]["answer"] == "refund"
    assert c["hypothetical"] is False and c["rule_version"] == "v2"
    assert answers[0]["citation"] == c["citation"] and "cites" not in answers[0]
    assert "no flight date" in unusable[0][2]
    assert "no stated answer" in unusable[0][2]


def test_saved_pages_every_example_is_a_case_or_listed():
    # @criterion C6
    cases, answers, unusable = dot.build()
    assert {a["case_id"] for a in answers} == {c["case_id"] for c in cases}
    out = ROOT / "cases" / "test" / "dot"
    on_disk = [json.loads(x) for x in (out / "cases.jsonl").read_text().splitlines()]
    assert on_disk == json.loads(json.dumps(cases))
    md = (out / "unusable.md").read_text()
    assert all(ref in md for ref, _, _ in unusable)


def test_held_out_answers_only_under_labels_and_no_dot_in_dev():
    # @criterion C6
    dev = [
        json.loads(x) for x in (ROOT / "cases/dev/cases.jsonl").read_text().splitlines()
    ]
    assert not [
        c
        for c in dev
        if c.get("source") == "dot" or str(c["case_id"]).startswith("dot-")
    ]
    for line in (ROOT / "cases/test/dot/cases.jsonl").read_text().splitlines():
        assert "answer" not in json.loads(line)
    assert (ROOT / "data/labels/dot/answers.jsonl").exists()


FIXTURES = ROOT / "tests" / "fixtures" / "dot"


def test_hypothetical_guide_examples_become_cases(tmp_path):
    # @criterion C6
    guide = f"{dot.GUIDE}.txt"
    shutil.copy(FIXTURES / guide, tmp_path / guide)
    (tmp_path / f"{dot.GUIDE}.pdf").write_bytes(b"%PDF-1.4\n")  # text from a PDF
    cases, answers, unusable = dot.build(tmp_path)
    assert len(cases) == 2 and len(answers) == 2
    c = cases[0]
    assert c["case_id"] == f"dot-{dot.GUIDE}-p2"
    assert c["hypothetical"] is True and c["bts_flight"] is None
    assert c["carrier"] is None and c["flight_number"] is None
    assert c["flight_date"] is None and c["rule_version"] == "v2"
    assert c["type"] == "dot_example" and c["source"] == "dot"
    assert c["citation"]["file"] == f"rules/sources/dot/{guide}"
    assert c["citation"]["paragraph"] == 2 and c["citation"]["page"] == 1
    assert set(c["facts"]) == {"event", "size", "passenger_choice", "example_text"}
    assert all(f["from"] == "dot" for f in c["facts"].values())
    assert c["facts"]["event"]["value"] == "cancels"
    assert c["facts"]["passenger_choice"]["value"] == "does not accept"
    assert c["message"].startswith("If an airline cancels")
    assert answers[0] == {
        "case_id": c["case_id"],
        "answer": "refund",
        "rule_version": "v2",
        "citation": c["citation"],
    }
    assert answers[1]["answer"] == "no_refund"
    assert cases[1]["facts"]["size"]["value"] == "one hour"
    assert cases[1]["citation"]["page"] == 2
    assert cases[1]["facts"]["passenger_choice"]["value"] is None
    assert [(r.split()[-1], why) for r, _, why in unusable] == [
        ("4", "no stated answer")
    ]


def test_hypothetical_linked_from_the_guide_maps_to_v2(tmp_path):
    # @criterion C6
    shutil.copy(FIXTURES / f"{dot.GUIDE}.txt", tmp_path / "files-annex.txt")
    guide_url = "https://www.transportation.gov/airconsumer/Small_Entity_Guide_Refund_Final_Rule"
    manifest = {
        "files": [
            {"file": f"{dot.GUIDE}.html", "requested_url": guide_url},
            {"file": "files-annex.pdf", "requested_url": "x", "linked_from": guide_url},
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    cases, _, _ = dot.build(tmp_path)
    assert [c["rule_version"] for c in cases] == ["v2", "v2"]
    assert "page" not in cases[0]["citation"]  # no PDF beside it


def test_before_window_examples_listed_unusable(tmp_path):
    # @criterion C6
    faq = "airconsumer-FAQ-refunds-may-12-2020.txt"
    shutil.copy(FIXTURES / faq, tmp_path / faq)
    cases, answers, unusable = dot.build(tmp_path)
    assert cases == [] and answers == []
    assert len(unusable) == 1
    assert unusable[0][0] == f"rules/sources/dot/{faq} paragraph 2"
    assert unusable[0][2] == "before the study window (ADR-0001)"


def test_out_of_scope_example_listed_not_a_case(tmp_path):
    # @criterion C6
    page = tmp_path / f"{dot.GUIDE}.html"
    page.write_text(
        "<p>For example, if the airline delays the checked bag by 15 hours, the "
        "carrier must refund the bag fee.</p>"
        "<p>For example, if the airline cancels the flight and the consumer does not "
        "accept rebooking, the consumer is entitled to a refund.</p>"
    )
    cases, answers, unusable = dot.build(tmp_path)
    assert len(cases) == 1 and len(answers) == 1
    assert cases[0]["citation"]["paragraph"] == 2
    assert [(r.split()[-1], why) for r, _, why in unusable] == [
        ("1", "out of scope (pitch, No-gos)")
    ]
