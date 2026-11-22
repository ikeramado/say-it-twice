"""The naive agent: every version in the prompt, a parsed JSON answer (C2)."""

import json

import pytest

import runner
from agents import AGENTS, cheap_strong, naive
from agents.system import tools
from llm import Gate
from llm import provider as providers
from tests import test_agent_view as tv
from tests.test_agent_view import a_case, fake_gate, flights  # noqa: F401

ANSWER = {
    "decision": "refund",
    "clause": "AA-2024-04-12-x",
    "rule_version": "v1",
    "policy_version": "AA-2024-04-12",
    "explanation": "Your flight was significantly delayed.",
}


def test_prefix_holds_every_rule_and_policy_clause():
    # @criterion C2
    p = naive.prefix()
    rules = tools.all_rule_versions()
    assert len(rules) >= 5
    for v in rules:
        assert f"Rule version {v.id}" in p
        for c in v.clauses:
            assert c.id in p and c.text in p
    for carrier in ("AA", "DL"):
        versions = tools.all_policy_versions(carrier)
        assert versions
        for v in versions:
            assert f"Policy version {v.id}" in p
            for c in v.clauses:
                assert c.id in p and c.text in p
    assert tools.all_policy_versions("XX") == ()


def test_prompt_holds_flight_record_facts_and_message(flights):  # noqa: F811
    # @criterion C2
    p = naive.prompt(a_case())
    assert "cancelled: no" in p and "arrival delay: 152 minutes" in p
    assert "arrival_delay_min: 152" in p and 'purchase_date: "2024-07-23"' in p
    assert "My flight arrived late, refund me." in p


def test_answer_is_parsed_and_sent_with_the_prefix(tmp_path, flights):  # noqa: F811
    # @criterion C2
    calls = []
    gate = fake_gate(tmp_path, [json.dumps(ANSWER)], calls)
    out = naive.run(a_case(), gate.for_sample(3))
    for k, x in ANSWER.items():
        assert out[k] == x
    assert out["parse_error"] is False
    assert len(calls) == 1 and calls[0]["prefix"] == naive.prefix()
    assert calls[0]["prompt"] == naive.prompt(a_case())
    (line,) = out["trace"]
    assert line["sample"] == 3 and line["parse_error"] is False
    assert line["prompts_sha256"] == naive.prompt_hashes()
    assert set(line["prompts_sha256"]) == {"naive_system.txt", "naive_case.txt"}
    assert all(len(h) == 64 for h in line["prompts_sha256"].values())


def test_answer_inside_a_code_fence_is_parsed(tmp_path, flights):  # noqa: F811
    # @criterion C2
    text = "```json\n" + json.dumps(ANSWER) + "\n```"
    out = naive.run(a_case(), fake_gate(tmp_path, [text]).for_sample(0))
    assert out["decision"] == "refund" and out["parse_error"] is False


def test_bad_answers_become_escalate_with_parse_error(tmp_path, flights):  # noqa: F811
    # @criterion C2
    bad = ["not json at all", '{"decision": "maybe"}', "[1, 2]", '{"decision": ']
    gate = fake_gate(tmp_path, bad)
    for i in range(len(bad)):
        out = naive.run(a_case(), gate.for_sample(i))
        assert out["decision"] == "escalate"
        assert out["parse_error"] is True
        assert out["trace"][0]["parse_error"] is True


def test_model_comes_from_config():
    # @criterion C2
    from llm.provider import agent_model

    assert naive.MODEL == agent_model() and naive.CALLS_PER_CASE == 1


@pytest.mark.usefixtures("flights")
def test_stop_reason_in_trace(tmp_path):
    # @criterion C2
    # The failed run of 2026-11-19: thinking used all the output tokens, no text came back.
    def provider(model, prompt, max_output, prefix=None):
        return "", 100, 0, max_output, "max_tokens"

    g = Gate(
        tmp_path / "run", naive.MODEL, tv.PRICES, 10.0, tmp_path / "cache", provider
    )
    out = naive.run(a_case(), g.for_sample(0))
    assert out["decision"] == "escalate" and out["parse_error"] is True
    assert out["trace"][0]["stop_reason"] == "max_tokens"
    # a readable answer carries no stop reason in its line
    ok = fake_gate(tmp_path / "ok", [json.dumps(ANSWER)])
    assert "stop_reason" not in naive.run(a_case(), ok.for_sample(0))["trace"][0]


@pytest.mark.usefixtures("flights")
@pytest.mark.parametrize("name", ["naive", "cheap_strong", "system"])
def test_max_output_from_entry(tmp_path, monkeypatch, name):
    # @criterion C2
    agent = AGENTS[name]
    models = providers.load_models()
    models["models"][agent.MODEL] = {**models["models"][agent.MODEL], "max_output": 777}
    monkeypatch.setattr(providers, "load_models", lambda *a: models)
    seen = []

    def provider(model, prompt, max_output, prefix=None):
        seen.append(max_output)
        return json.dumps(ANSWER), 100, 0, 20, "end_turn"

    case = a_case()
    runner.run(name, [case], 1, "r", 10.0, 10.0, tmp_path / "runs", tv.PRICES, provider)
    assert seen and set(seen) == {777}
    e = runner.estimate(name, [case], 1, tv.PRICES)
    assert e["output_tokens"] == agent.CALLS_PER_CASE * 777


@pytest.mark.parametrize("agent", [naive, cheap_strong])
def test_dot_case_escalates_no_flight_without_a_call(agent, tmp_path):
    calls = []
    gate = fake_gate(tmp_path, [], calls)
    out = agent.run(tv.dot_case(), gate.for_sample(0))
    assert out["decision"] == "escalate" and out["clause"] == "no_flight"
    assert out["parse_error"] is False
    assert calls == []
