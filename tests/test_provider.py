"""The provider-neutral client, its prices and the costed estimate, with fake SDK clients."""

import json
from types import SimpleNamespace as NS

import pytest
import yaml

import runner
from llm import PROFILES, Gate, load_prices
from llm import provider as providers

MODELS = {
    "agents": "a",
    "models": {
        "a": {
            "provider": "anthropic",
            "model": "claude-x",
            "key_env": "T21_A_KEY",
            "max_output": 300,
        },
        "o": {
            "provider": "openai_compatible",
            "model": "local-x",
            "base_url": "http://localhost:9/v1",
            "key_env": "T21_O_KEY",
            "max_output": 300,
        },
        "bad": {
            "provider": "carrier-pigeon",
            "model": "x",
            "key_env": "T21_A_KEY",
            "max_output": 300,
        },
    },
}
PRICES = {
    m: {"input": 1.0, "cache_write": 1.25, "cached_input": 0.1, "output": 5.0}
    for m in ("a", "o")
}


class FakeAnthropic:
    made, requests = [], []

    def __init__(self, **kw):
        FakeAnthropic.made.append(kw)
        self.messages = self

    def create(self, **kw):
        FakeAnthropic.requests.append(kw)
        usage = NS(
            input_tokens=7,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=0,
            output_tokens=3,
        )
        return NS(
            content=[NS(type="thinking"), NS(type="text", text="refund")], usage=usage
        )


class FakeOpenAI:
    made, requests = [], []

    def __init__(self, **kw):
        FakeOpenAI.made.append(kw)
        self.chat = NS(completions=self)

    def create(self, **kw):
        FakeOpenAI.requests.append(kw)
        usage = NS(
            prompt_tokens=107,
            completion_tokens=3,
            prompt_tokens_details=NS(cached_tokens=100),
        )
        return NS(choices=[NS(message=NS(content="no_refund"))], usage=usage)


@pytest.fixture
def fakes(monkeypatch):
    for f in (FakeAnthropic, FakeOpenAI):
        f.made, f.requests = [], []
    monkeypatch.setattr(providers.anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.setattr(providers.openai, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(providers, "load_models", lambda *a: MODELS)
    monkeypatch.setenv("T21_A_KEY", "secret-a")
    monkeypatch.setenv("T21_O_KEY", "secret-o")
    return monkeypatch


def gate(tmp_path, model):
    return Gate(tmp_path / "r", model, PRICES, 10.0, tmp_path / "cache")


def test_anthropic_request_and_usage(tmp_path, fakes):
    # @criterion C8
    g = gate(tmp_path, "a")
    assert g.call("the case", 0, prefix="the rules") == "refund"
    assert FakeAnthropic.made == [{"api_key": "secret-a", "max_retries": 0}]
    (req,) = FakeAnthropic.requests
    assert req["model"] == "claude-x" and req["max_tokens"] == g.max_output
    assert req["system"] == [
        {"type": "text", "text": "the rules", "cache_control": {"type": "ephemeral"}}
    ]
    assert req["messages"] == [{"role": "user", "content": "the case"}]
    line = json.loads(g.costs.read_text())
    assert (line["input_tokens"], line["cached_tokens"], line["output_tokens"]) == (
        107,
        100,
        3,
    )
    assert "secret-a" not in g.costs.read_text()
    # no prefix: no system block
    g.call("other case", 0)
    assert "system" not in FakeAnthropic.requests[-1]


def test_openai_compatible_request_and_usage(tmp_path, fakes):
    # @criterion C8
    g = gate(tmp_path, "o")
    assert g.call("the case", 0, prefix="the rules") == "no_refund"
    assert FakeOpenAI.made == [
        {"api_key": "secret-o", "base_url": "http://localhost:9/v1", "max_retries": 0}
    ]
    (req,) = FakeOpenAI.requests
    assert req["model"] == "local-x" and req["max_completion_tokens"] == g.max_output
    assert req["messages"] == [
        {"role": "system", "content": "the rules"},
        {"role": "user", "content": "the case"},
    ]
    line = json.loads(g.costs.read_text())
    assert (line["input_tokens"], line["cached_tokens"], line["output_tokens"]) == (
        107,
        100,
        3,
    )


def test_openai_compatible_without_cache_report(tmp_path, fakes):
    # @criterion C8
    def create(self, **kw):
        usage = NS(prompt_tokens=50, completion_tokens=2, prompt_tokens_details=None)
        return NS(choices=[NS(message=NS(content="x"))], usage=usage)

    fakes.setattr(FakeOpenAI, "create", create)
    assert providers.real_provider("o", "p", 10) == ("x", 50, 0, 2, None, None)


@pytest.mark.parametrize("model,var", [("a", "T21_A_KEY"), ("o", "T21_O_KEY")])
def test_missing_key_raises_before_any_request(tmp_path, fakes, model, var):
    # @criterion C8
    fakes.delenv(var)
    with pytest.raises(providers.MissingKey, match=var):
        gate(tmp_path, model).call("p", 0)
    assert not FakeAnthropic.made and not FakeOpenAI.made
    assert not FakeAnthropic.requests and not FakeOpenAI.requests


def test_unknown_provider_kind_raises(fakes):
    # @criterion C8
    with pytest.raises(providers.UnknownProvider):
        providers.real_provider("bad", "p", 10)
    with pytest.raises(KeyError):
        providers.real_provider("nobody", "p", 10)
    assert not FakeAnthropic.made and not FakeOpenAI.made


def test_agents_model_comes_from_config():
    # @criterion C8
    models = providers.load_models()
    assert providers.agent_model() == "claude-haiku-5-5"
    for name in ("claude-haiku-5-5", "claude-sonnet-5-5"):
        e = providers.entry(name, models)
        assert e["provider"] == "anthropic" and e["model"] == name
        assert e["key_env"] == "ANTHROPIC_API_KEY"


def test_prices_have_every_field_and_source():
    # @criterion C8
    prices = load_prices()
    models = providers.load_models()["models"]
    fields = {
        "input",
        "cache_write",
        "cached_input",
        "output",
        "batch_input",
        "batch_cached_input",
        "batch_output",
    }
    for name in ("claude-haiku-5-5", "claude-sonnet-5-5"):
        assert name in models
        p = prices[name]
        assert fields <= set(p)
        assert all(isinstance(p[f], float) and p[f] > 0 for f in fields)
        assert p["source"].startswith("https://") and p["read_on"] == "2026-11-18"
        assert p["cached_input"] < p["input"] < p["cache_write"]
        assert p["batch_input"] == pytest.approx(p["input"] / 2)
        assert p["batch_output"] == pytest.approx(p["output"] / 2)


def test_estimate_makes_no_call(monkeypatch, capsys):
    # @criterion C8
    def boom(*a, **k):
        raise AssertionError("a model client was made or called")

    monkeypatch.setattr(providers.anthropic, "Anthropic", boom)
    monkeypatch.setattr(providers.openai, "OpenAI", boom)
    monkeypatch.setattr(providers, "real_provider", boom)
    est = runner.estimate_study("all")
    protocols = ("dev-subset", "dev-full", "confirm")
    assert set(est) == {(a, p) for a in PROFILES for p in protocols}
    case_runs = runner.protocols()
    assert case_runs["dev-subset"] == 120 and case_runs["dev-full"] == 1850
    assert case_runs["confirm"] >= 1300
    prefix = runner.prefix_tokens()
    price = load_prices()["claude-haiku-5-5"]
    for (agent, proto), e in est.items():
        calls = case_runs[proto] * PROFILES[agent]
        assert e["calls"] == calls
        assert e["cached_tokens"] == (calls - 1) * prefix
        assert e["input_tokens"] == calls * 300 + calls * prefix
        assert e["output_tokens"] == calls * 300
        want = (
            calls * 300 * price["input"]
            + prefix * price["cache_write"]
            + (calls - 1) * prefix * price["cached_input"]
            + calls * 300 * price["output"]
        ) / 1e6
        assert e["dollars"] == pytest.approx(want)
        assert 0 < e["batch_dollars"] < e["dollars"]
    assert sum(e["dollars"] for e in est.values()) < 100  # the card's escalation line
    runner.main(["estimate", "--protocol", "all"])
    out = capsys.readouterr().out
    for agent in PROFILES:
        for proto in protocols:
            assert any(agent in line and proto in line for line in out.splitlines())
    assert "total dollars" in out


def test_smoke_reports_cache_hit(tmp_path, fakes):
    # @criterion C8
    fakes.setattr(providers, "load_models", lambda *a: MODELS)
    lines = runner.smoke("a", runs_dir=tmp_path, prices=PRICES)
    assert [x["cache"] for x in lines] == [False, True]
    assert len(FakeAnthropic.requests) == 1 and lines[1]["dollars"] == 0


def yaml_models():
    return yaml.safe_load(providers.MODELS_PATH.read_text())


def test_params_reach_request(tmp_path, fakes):
    # @criterion C2
    # The agents' entry turns thinking off and allows 1024 output tokens (T27); whether the
    # real model accepts it is the provider's documentation and the human's next real run.
    models = yaml_models()
    e = models["models"][models["agents"]]
    assert e["params"] == {"thinking": {"type": "disabled"}}
    assert e["max_output"] == 1024
    fakes.setattr(providers, "load_models", lambda *a: models)
    fakes.setenv(e["key_env"], "secret-real")
    prices = {models["agents"]: PRICES["a"]}
    g = Gate(tmp_path / "r", models["agents"], prices, 10.0, tmp_path / "cache")
    assert g.call("the case", 0, prefix="the rules") == "refund"
    (req,) = FakeAnthropic.requests
    assert req["thinking"] == {"type": "disabled"}
    assert req["max_tokens"] == 1024 == g.max_output


def test_every_entry_has_max_output_and_a_missing_one_raises():
    # @criterion C2
    models = yaml_models()
    for name in models["models"]:
        assert providers.max_output(name, models) >= 1
    broken = {"models": {"x": {**MODELS["models"]["a"]}}}
    del broken["models"]["x"]["max_output"]
    with pytest.raises(providers.MissingMaxOutput):
        providers.entry("x", broken)
    with pytest.raises(providers.MissingMaxOutput):
        providers.max_output("x", broken)
    # a model with no entry: the placeholder's fixed budget
    assert providers.max_output("placeholder") == providers.PLACEHOLDER_MAX_OUTPUT
    assert providers.max_output("no-such-model", models) == 300


def answer(*blocks, stop):
    usage = NS(
        input_tokens=7,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        output_tokens=300,
    )
    return NS(content=list(blocks), usage=usage, stop_reason=stop)


def test_text_block_after_thinking(tmp_path, fakes):
    # @criterion C2
    replies = [
        answer(
            NS(type="thinking", thinking=""),
            NS(type="text", text='{"decision": "refund"}'),
            stop="end_turn",
        ),
        answer(NS(type="thinking", thinking=""), stop="max_tokens"),
    ]
    fakes.setattr(FakeAnthropic, "create", lambda self, **kw: replies.pop(0))
    g = gate(tmp_path, "a")
    assert g.call("case one", 0) == '{"decision": "refund"}'
    assert g.last_stop_reason == "end_turn"
    # thinking used the whole budget: no text, a parse error for the agent
    assert g.call("case two", 0) == ""
    assert g.last_stop_reason == "max_tokens"


def test_response_model_of_both_providers(tmp_path, fakes):
    # @criterion C8
    def served(fake, name):
        real = fake.create

        def create(self, **kw):
            r = real(self, **kw)
            r.model = name
            return r

        fakes.setattr(fake, "create", create)

    # a response with no model field gives null
    gate(tmp_path, "a").call("no model field", 0)
    assert json.loads(gate(tmp_path, "a").costs.read_text())["response_model"] is None
    served(FakeAnthropic, "claude-x-20261101")
    served(FakeOpenAI, "local-x-q4")
    for model, name in (("a", "claude-x-20261101"), ("o", "local-x-q4")):
        g = Gate(tmp_path / model, model, PRICES, 10.0, tmp_path / "cache")
        g.call("the case", 0)
        g.call("the case", 0)  # the cache answers, with the model cached with it
        lines = [json.loads(x) for x in g.costs.read_text().splitlines()]
        assert [(x["cache"], x["response_model"]) for x in lines] == [
            (False, name),
            (True, name),
        ]
