"""The cheap-strong agent: five samples per run, majority, tie gives escalate (C2)."""

import json

from agents import cheap_strong, naive
from tests.test_agent_view import a_case, fake_gate, flights  # noqa: F401

O = cheap_strong.OFFSET


def answer(decision, clause="c"):
    return json.dumps(
        {
            "decision": decision,
            "clause": clause,
            "rule_version": "v1",
            "policy_version": "AA-2024-04-12",
            "explanation": f"because {clause}",
        }
    )


def test_five_calls_majority_first_majority_sample(tmp_path, flights):  # noqa: F811
    # @criterion C2
    calls = []
    votes = [
        answer("no_refund", "a"),
        answer("refund", "b"),
        answer("refund", "c"),
        answer("escalate", "d"),
        answer("refund", "e"),
    ]
    gate = fake_gate(tmp_path, votes, calls)
    out = cheap_strong.run(a_case(), gate.for_sample(0))
    assert len(calls) == 5
    assert all(c["prefix"] == naive.prefix() for c in calls)
    assert out["decision"] == "refund" and out["clause"] == "b"
    assert out["explanation"] == "because b" and out["parse_error"] is False
    assert [t["sample"] for t in out["trace"][:5]] == [O, O + 1, O + 2, O + 3, O + 4]


def test_tie_gives_escalate(tmp_path, flights):  # noqa: F811
    # @criterion C2
    votes = [
        answer("refund"),
        answer("no_refund"),
        answer("refund"),
        answer("no_refund"),
        answer("escalate"),
    ]
    out = cheap_strong.run(a_case(), fake_gate(tmp_path, votes).for_sample(0))
    assert out["decision"] == "escalate" and out["clause"] == "tie"
    assert out["parse_error"] is False


def test_runs_zero_and_one_use_offset_samples(tmp_path, flights):  # noqa: F811
    # @criterion C2
    gate = fake_gate(tmp_path, [answer("refund")] * 10)
    first = cheap_strong.run(a_case(), gate.for_sample(0))
    second = cheap_strong.run(a_case(), gate.for_sample(1))
    assert [t["sample"] for t in first["trace"][:5]] == [O, O + 1, O + 2, O + 3, O + 4]
    assert [t["sample"] for t in second["trace"][:5]] == [
        O + 5,
        O + 6,
        O + 7,
        O + 8,
        O + 9,
    ]
    cached = [json.loads(x)["cache"] for x in gate.costs.read_text().splitlines()]
    assert cached == [False] * 10


def test_parse_errors_vote_as_escalate(tmp_path, flights):  # noqa: F811
    # @criterion C2
    votes = ["junk", "junk", "junk", answer("refund"), answer("refund")]
    out = cheap_strong.run(a_case(), fake_gate(tmp_path, votes).for_sample(0))
    assert out["decision"] == "escalate" and out["parse_error"] is True


def test_calls_per_case_and_model():
    # @criterion C2
    assert cheap_strong.CALLS_PER_CASE == 5 and cheap_strong.MODEL == naive.MODEL
    assert cheap_strong.prefix() == naive.prefix()


def test_own_samples_none_shared_with_naive(tmp_path, flights):  # noqa: F811
    # @criterion C2
    gate = fake_gate(tmp_path, [answer("refund")] * 100)
    cs = set()
    for i in range(10):
        out = cheap_strong.run(a_case(), gate.for_sample(i))
        got = [t["sample"] for t in out["trace"][:5]]
        assert got == [1_000_000 + 5 * i + k for k in range(5)]
        cs.update(got)
    assert cs.isdisjoint(range(10))
