"""The agents' view of a case hides what would leak the answer (C2)."""

import csv
import json
from pathlib import Path

import pytest

from agents import cheap_strong, naive
from agents.view import opaque_id, view
from llm import Gate

ROOT = Path(__file__).resolve().parent.parent
HIDDEN = ("type", "meta", "clean_case_id", "attack", "contradicts_facts", "bts_flight")
FLIGHT = {
    "carrier": "AA",
    "flight_number": "2895",
    "date": "2024-09-15",
    "origin": "CLT",
    "destination": "DFW",
    "scheduled_departure": "0800",
    "actual_departure": "1030",
    "scheduled_arrival": "1000",
    "actual_arrival": "1232",
    "cancelled": "0",
    "diverted": "0",
    "cancellation_code": "",
    "departure_delay": "150",
    "arrival_delay": "152",
}
PRICES = {naive.MODEL: {"input": 1.0, "cached_input": 0.1, "output": 1.0}}


def a_case(**over):
    case = {
        "case_id": "dev-pol-001",
        "type": "policies_differ",
        "carrier": "AA",
        "flight_number": "2895",
        "flight_date": "2024-09-15",
        "origin": "CLT",
        "bts_flight": {"carrier": "AA", "date": "2024-09-15"},
        "facts": {
            "arrival_delay_min": {"value": 152, "constructed": False},
            "purchase_date": {"value": "2024-07-23", "constructed": True},
        },
        "message": {"text": "My flight arrived late, refund me.", "constructed": True},
        "meta": {"rule_version": "v1", "policy_version": "AA-2024-04-12"},
        "clean_case_id": "dev-pol-000",
        "attack": "authority",
        "contradicts_facts": True,
    }
    case.update(over)
    return case


@pytest.fixture
def flights(tmp_path, monkeypatch):
    """A data root holding the one flight of a_case()."""
    d = tmp_path / "data" / "clean" / "flights"
    d.mkdir(parents=True)
    with (d / "2024-09.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(FLIGHT))
        w.writeheader()
        w.writerow(FLIGHT)
    monkeypatch.setenv("SAY_IT_TWICE_DATA_ROOT", str(tmp_path))
    return tmp_path


def fake_gate(tmp_path, answers, calls=None):
    """A gate whose fake provider gives answers in turn and records each call."""
    calls = [] if calls is None else calls
    queue = list(answers)

    def provider(model, prompt, max_output, prefix=None):
        calls.append({"prompt": prompt, "prefix": prefix})
        return queue.pop(0), 100, 0, 20

    return Gate(
        tmp_path / "run", naive.MODEL, PRICES, 10.0, tmp_path / "cache", provider
    )


def test_view_hides_id_type_and_hidden_fields():
    # @criterion C2
    case = a_case()
    v = view(case)
    text = json.dumps(v)
    assert set(v) == {
        "id",
        "carrier",
        "flight_number",
        "flight_date",
        "origin",
        "facts",
        "message",
    }
    assert "dev-pol-001" not in text and "dev-pol" not in text
    assert "policies_differ" not in text and "constructed" not in text
    for key in HIDDEN:
        assert key not in v
    assert v["facts"] == {"arrival_delay_min": 152, "purchase_date": "2024-07-23"}
    assert v["message"] == "My flight arrived late, refund me."
    assert len(v["id"]) == 10 and v["id"] == opaque_id("dev-pol-001")


def test_two_cases_differing_in_id_and_type_differ_only_in_id():
    # @criterion C2
    a = view(a_case())
    b = view(a_case(case_id="dev-cxl-017", type="cancelled"))
    assert a["id"] != b["id"]
    assert {k: x for k, x in a.items() if k != "id"} == {
        k: x for k, x in b.items() if k != "id"
    }


def test_view_of_every_dev_case_leaks_nothing():
    # @criterion C2
    for line in (ROOT / "cases/dev/cases.jsonl").read_text().splitlines():
        case = json.loads(line)
        text = json.dumps(view(case))
        assert case["case_id"] not in text and "constructed" not in text
        assert not set(HIDDEN) & set(view(case))


def test_agents_prompts_hold_no_case_id():
    # @criterion C2
    case = a_case()
    for agent in (naive, cheap_strong):
        p = agent.prompt(case)
        assert "dev-pol-001" not in p and "policies_differ" not in p
        assert opaque_id("dev-pol-001") in p


@pytest.mark.parametrize("agent", [naive, cheap_strong])
def test_flight_not_found_gives_no_flight(agent, tmp_path, flights):
    # @criterion C2
    calls = []
    gate = fake_gate(tmp_path, [], calls)
    out = agent.run(a_case(flight_number="9999"), gate.for_sample(0))
    assert out["decision"] == "escalate"
    assert out["clause"] == "no_flight"
    assert out["parse_error"] is False
    assert calls == []


DOT_CASE = Path(__file__).resolve().parent.parent / "cases" / "test" / "dot" / "cases.jsonl"


def dot_case():
    return json.loads(DOT_CASE.read_text(encoding="utf-8").splitlines()[0])


def old_view(case):
    """The view as it was before T35, kept here to prove it did not change."""
    return {
        "id": opaque_id(case["case_id"]),
        "carrier": case["carrier"],
        "flight_number": str(case["flight_number"]),
        "flight_date": str(case["flight_date"]),
        "origin": case["origin"],
        "facts": {name: f["value"] for name, f in case["facts"].items()},
        "message": case["message"]["text"],
    }


def test_view_of_the_dot_case_has_no_flight_and_its_message():
    case = dot_case()
    v = view(case)
    assert [v[k] for k in ("carrier", "flight_number", "flight_date", "origin")] == [
        None
    ] * 4
    assert v["message"] == case["message"] and isinstance(v["message"], str)
    assert v["facts"]["event"] == "cancellation"


def test_view_unchanged_for_every_case_with_a_flight():
    root = Path(__file__).resolve().parent.parent / "cases"
    n = 0
    for name in ("dev", "test"):
        for line in (root / name / "cases.jsonl").read_text(encoding="utf-8").splitlines():
            case = json.loads(line)
            assert view(case) == old_view(case)
            n += 1
    assert n > 0
