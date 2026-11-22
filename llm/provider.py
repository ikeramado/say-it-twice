"""Providers: a provider is a callable
(model, prompt, max_output, prefix=None)
-> (text, input_tokens, cached_tokens, output_tokens, stop_reason, response_model).

`model` is an entry name of config/models.yaml; the entry names the provider kind, the API
model id and the environment variable that holds the key. input_tokens counts every input
token of the call (cached ones included); cached_tokens the ones read from the provider's
prompt cache; stop_reason is the provider's own (Anthropic `stop_reason`, OpenAI
`finish_reason`); response_model is the `model` field of the provider's response (None when
the response has none). Every entry has `max_output`, the output tokens of each call; a model with no
entry (the placeholder, a test's fake model) uses PLACEHOLDER_MAX_OUTPUT.
"""

import os
from pathlib import Path

import anthropic
import openai
import yaml

PLACEHOLDER_MODEL = "placeholder"
PLACEHOLDER_ANSWER = "no_refund"
MODELS_PATH = Path(__file__).resolve().parent.parent / "config" / "models.yaml"
KINDS = ("anthropic", "openai_compatible")
PLACEHOLDER_MAX_OUTPUT = 300


class MissingKey(Exception):
    """The environment variable a model entry names is not set; no request is made."""


class UnknownProvider(Exception):
    """A model entry names a provider kind the client does not know."""


class MissingMaxOutput(Exception):
    """A model entry has no `max_output`."""


def load_models(path=MODELS_PATH):
    return yaml.safe_load(Path(path).read_text())


def entry(model, models=None):
    models = models or load_models()
    try:
        e = models["models"][model]
    except KeyError:
        raise KeyError(f"no entry {model!r} in config/models.yaml") from None
    if e.get("provider") not in KINDS:
        raise UnknownProvider(
            f"entry {model!r}: provider {e.get('provider')!r} is not one of {KINDS}"
        )
    if not isinstance(e.get("max_output"), int) or e["max_output"] < 1:
        raise MissingMaxOutput(f"entry {model!r}: no max_output (a positive integer)")
    return e


def max_output(model, models=None):
    """The output tokens of each call of `model`: its entry's max_output, or
    PLACEHOLDER_MAX_OUTPUT for a model with no entry."""
    if model == PLACEHOLDER_MODEL:
        return PLACEHOLDER_MAX_OUTPUT
    models = models or load_models()
    if model not in models.get("models", {}):
        return PLACEHOLDER_MAX_OUTPUT
    return entry(model, models)["max_output"]


def agent_model(models=None):
    """The entry name the agents use (key `agents` of config/models.yaml)."""
    return (models or load_models())["agents"]


def _key(e):
    name = e["key_env"]
    value = os.environ.get(name)
    if not value:
        raise MissingKey(f"environment variable {name} is not set")
    return value


def _anthropic(e, key, prompt, max_output, prefix):
    # max_retries=0: the gate owns the retries (at most 2), so the SDK adds none.
    client = anthropic.Anthropic(api_key=key, max_retries=0)
    kw = dict(e.get("params") or {})
    if prefix is not None:
        kw["system"] = [
            {"type": "text", "text": prefix, "cache_control": {"type": "ephemeral"}}
        ]
    r = client.messages.create(
        model=e["model"],
        max_tokens=max_output,
        messages=[{"role": "user", "content": prompt}],
        **kw,
    )
    u = r.usage
    read = u.cache_read_input_tokens or 0
    written = u.cache_creation_input_tokens or 0
    # Thinking blocks come first when thinking is on; only text blocks are the answer.
    text = "".join(b.text for b in r.content if b.type == "text")
    stop = getattr(r, "stop_reason", None)
    served = getattr(r, "model", None)
    return text, u.input_tokens + read + written, read, u.output_tokens, stop, served


def _openai(e, key, prompt, max_output, prefix):
    client = openai.OpenAI(api_key=key, base_url=e["base_url"], max_retries=0)
    messages = [{"role": "user", "content": prompt}]
    if prefix is not None:
        messages.insert(0, {"role": "system", "content": prefix})
    r = client.chat.completions.create(
        model=e["model"],
        max_completion_tokens=max_output,
        messages=messages,
        **dict(e.get("params") or {}),
    )
    u = r.usage
    details = u.prompt_tokens_details
    cached = (details.cached_tokens or 0) if details is not None else 0
    choice = r.choices[0]
    text = choice.message.content or ""
    stop = getattr(choice, "finish_reason", None)
    served = getattr(r, "model", None)
    return text, u.prompt_tokens, cached, u.completion_tokens, stop, served


_CALLS = {"anthropic": _anthropic, "openai_compatible": _openai}


def placeholder(model, prompt, max_output, prefix=None):
    n_in = len((prefix or "") + prompt) // 4
    return PLACEHOLDER_ANSWER, n_in, 0, len(PLACEHOLDER_ANSWER) // 4, "end_turn", None


def real_provider(model, prompt, max_output, prefix=None, models=None):
    e = entry(model, models)
    key = _key(e)  # raises before any client exists
    return _CALLS[e["provider"]](e, key, prompt, max_output, prefix)


def get_provider(model):
    if model == PLACEHOLDER_MODEL:
        return placeholder
    # Looked up at call time, so a test that patches real_provider reaches every gate.
    return lambda *a, **k: real_provider(*a, **k)
