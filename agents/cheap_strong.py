"""The cheap-strong agent: the naive agent sampled five times per run, majority vote.

Run i uses sample indexes OFFSET + 5*i + k, k = 0..4: no two runs share a cached answer, and
none is shared with the naive agent, whose run i uses sample i. The output
takes the fields of the first sample that voted for the majority decision; a tie (2-2-1)
gives escalate with the clause `tie`.
"""

from collections import Counter

from agents import naive
from agents.view import view

MODEL = naive.MODEL
CALLS_PER_CASE = 5
OFFSET = 1_000_000
prefix = naive.prefix


def prompt(case):
    return naive.prompt(case)


def vote(answers):
    """The output of five parsed answers."""
    counts = Counter(a["decision"] for a in answers).most_common()
    if len(counts) > 1 and counts[0][1] == counts[1][1]:
        return {
            "decision": "escalate",
            "clause": "tie",
            "rule_version": None,
            "policy_version": None,
            "explanation": "the samples tied: "
            + ", ".join(f"{d} {n}" for d, n in counts),
            "parse_error": False,
        }
    top = counts[0][0]
    return dict(next(a for a in answers if a["decision"] == top))


def run(case, gate):
    v = view(case)
    rec = naive.flight(v)
    if rec is None:
        out = naive.no_flight(v)
        return {
            **out,
            "trace": [{"id": v["id"], "flight": "not found", "parse_error": False}],
        }
    answers, trace = [], []
    for k in range(CALLS_PER_CASE):
        out, line = naive.ask(
            v, rec, gate.gate.for_sample(OFFSET + CALLS_PER_CASE * gate.sample + k)
        )
        answers.append(out)
        trace.append(line)
    out = vote(answers)
    trace.append(
        {
            "id": v["id"],
            "votes": [a["decision"] for a in answers],
            "chosen": out["decision"],
        }
    )
    return {**out, "trace": trace}
