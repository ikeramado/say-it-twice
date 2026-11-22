"""Costed estimate of the study's protocols, with prompt caching, and no call made.

Fixed per-agent profiles until the agents exist (T21): calls per case-run; every call carries
the rule and policy texts as its cached prefix plus CASE_TOKENS of its own, and writes
OUTPUT_TOKENS. One cache write of the prefix per protocol and agent, cache reads after it.
"""

PROFILES = {"naive": 1, "cheap-strong": 5, "system": 2}
CASE_TOKENS = 300
OUTPUT_TOKENS = 300


def estimate_protocol(case_runs, calls_per_case_run, prefix_tokens, price):
    """Calls, input, cached and output tokens and dollars (standard and batch) of one
    protocol for one agent."""
    calls = case_runs * calls_per_case_run
    if calls == 0:
        cached = written = 0
    else:
        written = prefix_tokens  # the first call writes the prefix
        cached = (calls - 1) * prefix_tokens
    fresh = calls * CASE_TOKENS
    out = calls * OUTPUT_TOKENS

    def cost(inp, write, read, output):
        return (
            fresh * inp + written * write + cached * read + out * output
        ) / 1_000_000

    p = price
    return {
        "calls": calls,
        "input_tokens": fresh + written + cached,
        "cached_tokens": cached,
        "output_tokens": out,
        "dollars": cost(p["input"], p["cache_write"], p["cached_input"], p["output"]),
        # The batch discount stacks with the caching multipliers, the write included.
        "batch_dollars": cost(
            p["batch_input"],
            p["cache_write"] / 2,
            p["batch_cached_input"],
            p["batch_output"],
        ),
    }


def estimate_protocols(protocols, prefix_tokens, price, profiles=PROFILES):
    """{(agent, protocol): estimate}. protocols: {name: case-runs}."""
    return {
        (agent, name): estimate_protocol(case_runs, n, prefix_tokens, price)
        for agent, n in profiles.items()
        for name, case_runs in protocols.items()
    }
