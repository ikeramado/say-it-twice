import json
import threading
import time

import anthropic
import httpx2
import pytest

import runner
from llm import BudgetExceeded, CeilingReached, Gate
from llm import provider as providers

PRICES = {
    "m": {
        "input": 1000.0,
        "cache_write": 1250.0,
        "cached_input": 100.0,
        "output": 1000.0,
    },
    "placeholder": {"input": 0.0, "cached_input": 0.0, "output": 0.0},
}


def ok(model, prompt, n, prefix=None):
    return "answer", 10, 0, 10


def rate_limited(retry_after="0", status=429):
    """A real 429 (or other status) answer of the Anthropic client, with a retry-after header."""
    resp = httpx2.Response(
        status,
        headers={"retry-after": retry_after},
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    cls = anthropic.RateLimitError if status == 429 else anthropic.APIStatusError
    return cls("slow down", response=resp, body=None)


def gate(tmp_path, ceiling=100.0, provider=ok, sleep=lambda s: None):
    return Gate(
        tmp_path / "r", "m", PRICES, ceiling, tmp_path / "cache", provider, sleep
    )


def test_projected_budget_refuses_start(tmp_path):
    # @criterion C9
    cases = runner.synthetic_cases(2)
    calls = []
    with pytest.raises(BudgetExceeded):
        runner.run(
            "placeholder",
            cases,
            2,
            "r1",
            budget=-1.0,
            ceiling=1.0,
            runs_dir=tmp_path,
            provider=lambda *a: calls.append(a),
        )
    assert not calls and not (tmp_path / "r1" / "outputs").exists()


def test_ceiling_stops_before_call(tmp_path):
    # @criterion C9
    calls = []

    def p(*a):
        calls.append(a)
        return "x", 10, 0, 10

    g = gate(tmp_path, ceiling=0.5, provider=p)
    g.call("a" * 40, 0)
    n = len(calls)
    with pytest.raises(CeilingReached):
        for i in range(1, 50):
            g.call("a" * 40, i)
    assert len(calls) < 50 and g.total() <= 0.5 and len(calls) >= n


def test_retries_at_most_twice(tmp_path):
    # @criterion C9
    calls = []

    def bad(*a):
        calls.append(a)
        raise rate_limited()

    with pytest.raises(anthropic.RateLimitError):
        gate(tmp_path, provider=bad).call("hello", 0)
    assert len(calls) == 3


def test_retries_recover(tmp_path):
    # @criterion C9
    calls = []

    def flaky(*a):
        calls.append(a)
        if len(calls) < 3:
            raise rate_limited()
        return "fine", 1, 0, 1

    assert gate(tmp_path, provider=flaky).call("hello", 0) == "fine"


def test_no_provider_estimate_makes_no_call(tmp_path, monkeypatch):
    # @criterion C9
    def boom(*a, **k):
        raise AssertionError("provider called")

    monkeypatch.setattr(providers, "real_provider", boom)
    monkeypatch.setattr(providers, "placeholder", boom)
    e = runner.estimate("placeholder", runner.synthetic_cases(2), 10)
    assert e["calls"] == 20 and e["input_tokens"] > 0 and e["dollars"] == 0
    assert not (tmp_path / "r").exists()


def test_cost_line_fields(tmp_path):
    # @criterion C9
    g = gate(tmp_path)
    g.call("hello world", 0)
    line = json.loads(g.costs.read_text())
    assert {
        "model",
        "input_tokens",
        "cached_tokens",
        "output_tokens",
        "dollars",
        "latency",
    } <= set(line)


def test_prefix_changes_cache_key(tmp_path):
    # @criterion C8
    calls = []

    def p(model, prompt, n, prefix=None):
        calls.append((prompt, prefix))
        return f"answer to {prefix}", 10, 4, 10

    g = gate(tmp_path, provider=p)
    assert g.call("case", 0, prefix="rules A") == "answer to rules A"
    assert g.call("case", 0, prefix="rules A") == "answer to rules A"  # response cache
    assert len(calls) == 1
    assert g.call("case", 0, prefix="rules B") == "answer to rules B"
    assert g.call("case", 0) == "answer to None"
    assert calls == [("case", "rules A"), ("case", "rules B"), ("case", None)]
    lines = [json.loads(x) for x in g.costs.read_text().splitlines()]
    assert [x["cache"] for x in lines] == [False, True, False, False]
    assert lines[0]["cached_tokens"] == 4 and lines[3]["cached_tokens"] == 4
    # 6 uncached tokens at the cache-write rate, 4 cached, 10 output
    assert lines[0]["dollars"] == pytest.approx((6 * 1250 + 4 * 100 + 10 * 1000) / 1e6)


def test_bound_forwards_prefix(tmp_path):
    # @criterion C8
    seen = []

    def p(model, prompt, n, prefix=None):
        seen.append(prefix)
        return "x", 1, 0, 1

    gate(tmp_path, provider=p).for_sample(3).call("case", prefix="rules")
    assert seen == ["rules"]


def test_ceiling_is_cumulative_across_runs(tmp_path):
    # @criterion C9
    calls = []

    def p(*a):
        calls.append(a)
        return "x", 10, 0, 10

    first = Gate(
        tmp_path / "r1", "m", PRICES, 0.5, tmp_path / "cache", p, lambda s: None
    )
    for i in range(10):
        first.call("a" * 40, i)
    spent = first.total()
    assert 0.1 < spent < 0.5
    second = Gate(
        tmp_path / "r2", "m", PRICES, 0.5, tmp_path / "cache", p, lambda s: None
    )
    assert second.total() == pytest.approx(spent)
    n = len(calls)
    with pytest.raises(CeilingReached):
        for i in range(100, 150):
            second.call("a" * 40, i)
    assert len(calls) < n + 50 and second.total() <= 0.5


def test_budget_enforced_during_run(tmp_path):
    # @criterion C9
    calls = []

    def heavy(*a):
        calls.append(a)
        return (
            "x",
            100,
            0,
            100,
        )  # far more than the projection of a short prompt's input

    g = Gate(
        tmp_path / "r",
        "m",
        PRICES,
        100.0,
        tmp_path / "cache",
        heavy,
        lambda s: None,
        budget=0.7,
    )
    assert g.check_budget({"dollars": 0.3}, 0.7) is None  # the projection passes
    with pytest.raises(BudgetExceeded):
        for i in range(10):
            g.call("abcd", i)
    assert 1 <= len(calls) < 10 and g.run_total() <= 0.7


def test_empty_answer_not_cached(tmp_path):
    # @criterion C2
    replies = [("", 10, 0, 300, "max_tokens"), ("  \n", 10, 0, 300, "max_tokens")]
    replies.append(("answer", 10, 0, 5, "end_turn"))
    calls = []

    def provider(model, prompt, n, prefix=None):
        calls.append(prompt)
        return replies.pop(0)

    g = gate(tmp_path, provider=provider)
    assert g.call("p", 0) == "" and g.last_stop_reason == "max_tokens"
    assert g.call("p", 0) == "  \n"  # not answered from the cache: asked again
    assert not list((tmp_path / "cache").glob("*.json"))
    assert g.call("p", 0) == "answer" and g.last_stop_reason == "end_turn"
    assert len(calls) == 3
    # a readable answer is cached; a hit resets the stop reason and makes no call
    assert g.call("p", 0) == "answer" and g.last_stop_reason is None
    assert len(calls) == 3
    assert "stop" not in next((tmp_path / "cache").glob("*.json")).read_text()


def test_stop_reason_reset_and_old_providers(tmp_path):
    # @criterion C2
    g = gate(tmp_path, provider=lambda m, p, n, prefix=None: ("x", 1, 0, 1, "end_turn"))
    g.call("a", 0)
    assert g.last_stop_reason == "end_turn"
    b = g.for_sample(0)
    assert b.last_stop_reason is None  # a bound gate keeps its own
    b.call("a2")
    assert b.last_stop_reason == "end_turn"

    def fails(m, p, n, prefix=None):
        raise RuntimeError("down")

    g.provider = fails
    with pytest.raises(RuntimeError):
        g.call("b", 0)
    assert g.last_stop_reason is None
    # 4- and 3-field providers still work and report no stop reason
    for out in (("y", 1, 0, 1), ("z", 1, 1)):
        g.provider = lambda m, p, n, prefix=None, out=out: out
        assert g.call(out[0], 0) == out[0] and g.last_stop_reason is None


def test_max_output_from_entry_or_given(tmp_path, monkeypatch):
    # @criterion C2
    assert gate(tmp_path).max_output == providers.PLACEHOLDER_MAX_OUTPUT
    models = {
        "models": {
            "m": {
                "provider": "anthropic",
                "model": "x",
                "key_env": "K",
                "max_output": 555,
            }
        }
    }
    monkeypatch.setattr(providers, "load_models", lambda *a: models)
    assert gate(tmp_path).max_output == 555
    g = Gate(tmp_path / "r", "m", PRICES, 1.0, tmp_path / "c", ok, max_output=9)
    assert g.max_output == 9
    assert runner.estimate_run(["p"], 1, 1, "m", PRICES)["output_tokens"] == 555


def test_rate_limited_retry(tmp_path):
    # @criterion C9
    calls, sleeps = [], []

    def flaky(*a):
        calls.append(a)
        if len(calls) < 3:
            raise rate_limited("0")
        return "fine", 1, 0, 1

    g = gate(tmp_path, provider=flaky, sleep=sleeps.append)
    assert g.call("hello", 0) == "fine" and len(calls) == 3
    assert sleeps == [1, 2]  # max(retry-after 0, 2**attempt)
    # retry-after longer than the backoff is honoured; a 529 retries, a 400 does not
    calls.clear(), sleeps.clear()

    def slow(*a):
        calls.append(a)
        if len(calls) == 1:
            raise rate_limited("7", status=529)
        return "ok", 1, 0, 1

    g = gate(tmp_path, provider=slow, sleep=sleeps.append)
    assert g.call("other", 0) == "ok" and sleeps == [7]
    # a longer retry-after is capped at 60 seconds
    calls.clear(), sleeps.clear()

    def very_slow(*a):
        calls.append(a)
        if len(calls) == 1:
            raise rate_limited("3600")
        return "ok", 1, 0, 1

    g = gate(tmp_path, provider=very_slow, sleep=sleeps.append)
    assert g.call("capped", 0) == "ok" and sleeps == [60]
    calls.clear()

    def bad_request(*a):
        calls.append(a)
        raise rate_limited("0", status=400)

    with pytest.raises(anthropic.APIStatusError):
        gate(tmp_path, provider=bad_request).call("third", 0)
    assert len(calls) == 1
    # a rate-limited call that never succeeds leaves no reservation behind
    g = gate(tmp_path, provider=lambda *a: (_ for _ in ()).throw(rate_limited()))
    with pytest.raises(anthropic.RateLimitError):
        g.call("fourth", 0)
    assert g._reserved == 0


def test_concurrent_budget_and_ceiling(tmp_path):
    # @criterion C9
    max_out = 100
    # worst case of one call: project_tokens("a"*40)=10 input, 100 output, at 1000 per million
    worst = (10 * 1000 + max_out * 1000) / 1_000_000
    n = 5
    for kind in ("budget", "ceiling"):
        _concurrent(tmp_path, kind, worst, n, max_out)


def _concurrent(tmp_path, kind, worst, n, max_out):
    started, lock = [], threading.Lock()

    def prov(m, p, k, prefix=None):
        with lock:
            started.append(p)
        time.sleep(0.02)
        return "x", 10, 0, k

    limit = worst * n + worst / 2
    g = Gate(
        tmp_path / kind / "r",
        "m",
        PRICES,
        limit if kind == "ceiling" else 100.0,
        tmp_path / kind / "cache",
        prov,
        lambda s: None,
        max_output=max_out,
        budget=limit if kind == "budget" else None,
    )
    errors = []

    def one(i):
        try:
            g.call("a" * 40, i)
        except (BudgetExceeded, CeilingReached) as e:
            errors.append(e)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(started) <= n
    assert len(errors) == 16 - len(started) and errors
    assert g.run_total() <= limit and g.total() <= limit
    assert g._reserved == pytest.approx(0)
    lines = [json.loads(x) for x in g.costs.read_text().splitlines()]
    assert sum(x["dollars"] for x in lines) <= limit


def connection_error(timeout=False):
    """A real connection error (or timeout) of the Anthropic client, as a cut network gives."""
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    if timeout:
        return anthropic.APITimeoutError(request=req)
    return anthropic.APIConnectionError(message="Network is unreachable", request=req)


def test_connection_error_retries(tmp_path):
    # @criterion C9
    import openai

    from llm.gate import is_network_error

    calls, sleeps = [], []

    def flaky(*a):
        calls.append(a)
        if len(calls) <= 2:
            raise connection_error(timeout=len(calls) == 2)
        return "fine", 1, 0, 1

    g = gate(tmp_path, provider=flaky, sleep=sleeps.append)
    assert g.call("hello", 0) == "fine" and len(calls) == 3 and sleeps == [2, 4]
    calls.clear(), sleeps.clear()

    def down(*a):
        calls.append(a)
        raise connection_error()

    g = gate(tmp_path, provider=down, sleep=sleeps.append)
    with pytest.raises(anthropic.APIConnectionError):
        g.call("cut", 0)
    assert len(calls) == 5 and sleeps == [2, 4, 8, 16]
    assert g._reserved == 0
    # nothing was cached: the same call asks the provider again
    calls.clear()
    with pytest.raises(anthropic.APIConnectionError):
        g.call("cut", 0)
    assert len(calls) == 5
    # both clients' connection errors are network errors; a 429 or a ValueError is not
    req = httpx2.Request("POST", "https://example.invalid/v1/chat/completions")
    assert is_network_error(openai.APIConnectionError(request=req))
    assert is_network_error(openai.APITimeoutError(request=req))
    assert not is_network_error(rate_limited()) and not is_network_error(ValueError())
    # 429 keeps its two retries
    calls.clear(), sleeps.clear()

    def limited(*a):
        calls.append(a)
        raise rate_limited()

    with pytest.raises(anthropic.RateLimitError):
        gate(tmp_path, provider=limited, sleep=sleeps.append).call("rl", 0)
    assert len(calls) == 3 and sleeps == [1, 2]


def test_response_model_on_cost_line_and_cache_hit(tmp_path):
    # @criterion C8
    def served(model, prompt, n, prefix=None):
        return "answer", 10, 0, 10, "end_turn", "m-2026-11-01"

    g = gate(tmp_path, provider=served)
    g.call("first", 0)
    g.call("first", 0)
    lines = [json.loads(x) for x in g.costs.read_text().splitlines()]
    assert [(x["cache"], x["response_model"]) for x in lines] == [
        (False, "m-2026-11-01"),
        (True, "m-2026-11-01"),
    ]
    # an older provider (5 fields or fewer) and an older cache entry give null
    old = gate(tmp_path / "old", provider=ok)
    old.call("second", 0)
    old.cache.put("m", "third", 0, {"text": "x", "input_tokens": 1, "output_tokens": 1})
    old.call("third", 0)
    lines = [json.loads(x) for x in old.costs.read_text().splitlines()]
    assert [(x["cache"], x["response_model"]) for x in lines] == [
        (False, None),
        (True, None),
    ]
