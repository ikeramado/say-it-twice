"""The system agent: facts by tools, the engine decides, the model only explains (C3, C11)."""

import csv
import json

from agents import AGENTS
from agents.system import agent
from tests import test_agent_view as tv
from tests.test_agent_view import a_case, fake_gate


def write_flight(tmp_path, monkeypatch, **over):
    d = tmp_path / "data" / "clean" / "flights"
    d.mkdir(parents=True)
    row = {**tv.FLIGHT, **over}
    with (d / "2024-09.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)
    monkeypatch.setenv("SAY_IT_TWICE_DATA_ROOT", str(tmp_path))


def run(tmp_path, case, answer="You are owed a refund."):
    calls = []
    gate = fake_gate(tmp_path, [answer], calls)
    return agent.run(case, gate.for_sample(0)), calls


def test_registered_with_two_calls_and_a_model():
    # @criterion C11
    assert AGENTS["system"] is agent and agent.CALLS_PER_CASE == 2
    assert agent.MODEL


def test_engine_decides_whatever_the_model_says(tmp_path, monkeypatch):
    # @criterion C3
    write_flight(tmp_path, monkeypatch, arrival_delay="20")
    case = a_case(facts={"purchase_date": {"value": "2024-07-23", "constructed": True}})
    out, calls = run(tmp_path, case)
    assert out["decision"] == "no_refund" and out["parse_error"] is False
    cite = f"[{out['rule_version']} / {out['clause']} / {out['policy_version']}]"
    assert out["explanation"].startswith("You are owed a refund.")
    assert out["explanation"].endswith(cite)
    assert len(calls) == 1 and "no_refund" in calls[0]["prompt"]
    (line,) = out["trace"]
    assert set(line) >= {
        "tool_calls",
        "facts",
        "rule_version",
        "policy_versions",
        "engine",
        "triggers",
        "explanation_prompt_sha256",
    }
    assert line["engine"]["decision"] == "no_refund" and line["triggers"] == []
    assert line["facts"]["arrival_delay_min"] == 20
    assert [c["tool"] for c in line["tool_calls"]] == [
        "get_flight",
        "get_rule",
        "get_policy",
    ]


def test_policy_scoped_to_the_cases_carrier(tmp_path, monkeypatch):
    # @criterion C3
    write_flight(tmp_path, monkeypatch, arrival_delay="20")
    for facts in (
        {"purchase_date": {"value": "2024-07-23", "constructed": True}},
        {},  # purchase date missing: every version of the one carrier
    ):
        out, _calls = run(tmp_path, a_case(facts=facts))
        (line,) = out["trace"]
        assert line["policy_versions"]
        assert all(p.startswith("AA") for p in line["policy_versions"])
        text = json.dumps(line)
        assert "DL-" not in text
        assert all(
            c["tool"] in ("get_flight", "get_rule", "get_policy", "purchase_candidates")
            and (c["tool"] == "get_flight" or "DL" not in json.dumps(c))
            for c in line["tool_calls"]
        )


def test_trigger_escalate_overrides_the_engine(tmp_path, monkeypatch):
    # @criterion C3
    write_flight(tmp_path, monkeypatch, arrival_delay="178")
    triggers = tmp_path / "triggers.yaml"
    triggers.write_text("window_minutes: 10\namount_threshold: null\n")
    monkeypatch.setattr(agent, "TRIGGERS", triggers)
    case = a_case(facts={"purchase_date": {"value": "2024-07-23", "constructed": True}})
    out, _calls = run(tmp_path, case, answer="Refund.")
    (line,) = out["trace"]
    assert "boundary" in line["triggers"]
    assert out["decision"] == "escalate" and "boundary" in out["clause"]
    assert line["engine"]["decision"] in ("refund", "no_refund")
    assert "boundary" in out["explanation"]


def test_conversion_of_the_flight_record(tmp_path, monkeypatch):
    # @criterion C3
    write_flight(tmp_path, monkeypatch, cancelled="1", arrival_delay="")
    out, _calls = run(tmp_path, a_case(facts={}))
    f = out["trace"][0]["facts"]
    assert f["cancelled"] is True and f["renumbered"] is False
    assert "arrival_delay_min" not in f


def test_flight_not_found_escalates_without_a_call(tmp_path, monkeypatch):
    # @criterion C3
    write_flight(tmp_path, monkeypatch)
    out, calls = run(tmp_path, a_case(flight_number="9999"))
    assert out["decision"] == "escalate" and out["clause"] == "no_flight"
    assert calls == []


def test_gap_purchase_date_lists_every_candidate(tmp_path, monkeypatch):
    # @criterion C3
    write_flight(tmp_path, monkeypatch, arrival_delay="20")
    case = a_case(facts={"purchase_date": {"value": "2024-08-01", "constructed": True}})
    out, _calls = run(tmp_path, case)
    (line,) = out["trace"]
    (call,) = [c for c in line["tool_calls"] if c["tool"] == "get_policy"]
    assert call["result"] == ["AA-2024-04-12", "AA-2024-07-25"]
    assert line["policy_versions"] == ["AA-2024-04-12", "AA-2024-07-25"]
    assert out["policy_version"] == "AA-2024-04-12;AA-2024-07-25"
    assert not any(t.startswith("missing_fact") for t in line["triggers"])


def test_purchase_candidates_call_lists_ids_and_null(tmp_path, monkeypatch):
    # @criterion C3
    write_flight(tmp_path, monkeypatch, arrival_delay="20", date="2024-08-05")
    flights = tmp_path / "data" / "clean" / "flights"
    (flights / "2024-09.csv").rename(flights / "2024-08.csv")
    case = a_case(flight_date="2024-08-05", facts={})
    out, _calls = run(tmp_path, case)
    (line,) = out["trace"]
    (call,) = [c for c in line["tool_calls"] if c["tool"] == "purchase_candidates"]
    assert call["result"] == ["AA-2023-10-10", "AA-2024-04-12", "AA-2024-07-25", None]
    assert line["policy_versions"] == [
        "AA-2023-10-10",
        "AA-2024-04-12",
        "AA-2024-07-25",
    ]


def test_dot_case_escalates_no_flight_with_no_call_and_a_skipped_trace(tmp_path):
    calls = []
    gate = fake_gate(tmp_path, [], calls)
    out = agent.run(tv.dot_case(), gate.for_sample(0))
    assert out["decision"] == "escalate" and out["clause"] == "no_flight"
    assert calls == []
    (line,) = out["trace"]
    assert line["skipped"] == "no flight" and line["tool_calls"] == []
