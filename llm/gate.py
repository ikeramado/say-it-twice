"""One gate for every model call: projection, budget, ceiling, retries, cost log, cache."""

import json
import threading
import time
from pathlib import Path

import anthropic
import openai
import yaml

from llm import provider as providers
from llm.cache import Cache

MAX_RETRIES = 2
MAX_NETWORK_RETRIES = 4  # a connection error or a timeout: waits 2, 4, 8, 16 s
MAX_RETRY_AFTER = 60.0  # seconds; a longer `retry-after` waits this long
PRICES_PATH = Path(__file__).resolve().parent.parent / "config" / "prices.yaml"


class BudgetExceeded(Exception):
    """The run's projected cost passes its budget; the run does not start."""


class CeilingReached(Exception):
    """The next call would pass the ceiling; it is not made."""


def _retry_after(exc):
    """The `retry-after` seconds of a provider's answer, 0 when absent or unreadable."""
    try:
        return min(
            MAX_RETRY_AFTER, max(0.0, float(exc.response.headers["retry-after"]))
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return 0.0


def retryable(exc):
    """A rate-limit, server-side or overloaded (529) answer; any other exception is not retried."""
    if isinstance(
        exc,
        (
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            openai.RateLimitError,
            openai.InternalServerError,
        ),
    ):
        return True
    return isinstance(exc, anthropic.APIStatusError) and exc.status_code == 529


def is_network_error(exc):
    """A connection error or a timeout of either client (the timeout is a subclass): the
    network, not the provider, failed. Retried up to MAX_NETWORK_RETRIES; the runner records
    a case-run that still fails on one as a failed output instead of stopping the run."""
    return isinstance(exc, (anthropic.APIConnectionError, openai.APIConnectionError))


def retry_wait(exc, attempt):
    """Seconds to wait before retrying `exc` after attempt `attempt` (0-based), or None when
    it is not retried: a network error waits 2**(attempt+1) up to MAX_NETWORK_RETRIES times;
    429, 5xx and 529 wait max(retry-after, 2**attempt) up to MAX_RETRIES times."""
    if is_network_error(exc):
        return 2 ** (attempt + 1) if attempt < MAX_NETWORK_RETRIES else None
    if retryable(exc):
        return max(_retry_after(exc), 2**attempt) if attempt < MAX_RETRIES else None
    return None


def load_prices(path=PRICES_PATH):
    return yaml.safe_load(Path(path).read_text())


def project_tokens(prompt):
    """Input tokens projected as characters / 4 (the provider's own count is in the cost line)."""
    return max(1, len(prompt) // 4)


def dollars(price, input_tokens, cached_tokens, output_tokens, prefixed=False):
    """Dollars of one call. With a cacheable prefix, the uncached input is charged at the
    cache-write rate: the provider may have written the prefix, and the 4-field usage of the
    provider contract does not say which part it wrote, so the gate errs high."""
    fresh = input_tokens - cached_tokens
    rate = price.get("cache_write", price["input"]) if prefixed else price["input"]
    return (
        fresh * max(rate, price["input"])
        + cached_tokens * price["cached_input"]
        + output_tokens * price["output"]
    ) / 1_000_000


def _ask(provider, model, prompt, max_output, prefix):
    """One provider call, as (text, input, cached, output, stop_reason, response_model)."""
    if prefix is None:
        out = provider(model, prompt, max_output)
    else:
        out = provider(model, prompt, max_output, prefix=prefix)
    if len(out) == 3:  # a provider written before the cached field reports none
        text, n_in, n_out = out
        out = (text, n_in, 0, n_out)
    # A provider written before the stop reason or the response model reports None for them.
    return (*out, *(None,) * (6 - len(out)))


def estimate_run(prompts, runs, calls_per_prompt, model, prices, max_output=None):
    """Calls, tokens and dollars of a run, with no call made. prompts: one per case.
    max_output: the model entry's own unless given."""
    price = prices[model]
    if max_output is None:
        max_output = providers.max_output(model)
    calls = len(prompts) * runs * calls_per_prompt
    in_tok = sum(project_tokens(p) for p in prompts) * runs * calls_per_prompt
    out_tok = calls * max_output
    return {
        "calls": calls,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "dollars": dollars(price, in_tok, 0, out_tok),
    }


def _file_total(path):
    if not path.exists():
        return 0.0
    return sum(json.loads(line)["dollars"] for line in path.read_text().splitlines())


class Gate:
    def __init__(
        self,
        run_dir,
        model,
        prices,
        ceiling,
        cache_dir,
        provider=None,
        sleep=time.sleep,
        max_output=None,
        budget=None,
    ):
        self.run_dir = Path(run_dir)
        self.model = model
        self.price = prices[model]
        self.ceiling = ceiling
        self.cache = Cache(cache_dir)
        self.provider = provider or providers.get_provider(model)
        self.sleep = sleep
        # The model entry's max_output unless the caller gives one (a test, the smoke call).
        self.max_output = (
            providers.max_output(model) if max_output is None else max_output
        )
        # The stop reason of the last real response; None after a cache hit or a failure.
        self.last_stop_reason = None
        self.costs = self.run_dir / "costs.jsonl"
        self.budget = budget
        # The ceiling covers every run: seed once from all runs/*/costs.jsonl, then keep in memory.
        self._all = sum(
            _file_total(f) for f in self.run_dir.parent.glob("*/costs.jsonl")
        )
        self._run = _file_total(self.costs)
        # The worst case of every call in flight; one lock guards the totals and the file.
        self._reserved = 0.0
        self._lock = threading.Lock()

    def check_budget(self, projection, budget):
        if projection["dollars"] > budget:
            raise BudgetExceeded(
                f"projected ${projection['dollars']:.4f} passes budget ${budget:.4f}"
            )

    def total(self):
        """Dollars spent by every run so far (what the ceiling bounds)."""
        return self._all

    def run_total(self):
        return self._run

    def _log(self, line, lines=None, release=0.0):
        """Append one cost line, replacing a reservation of `release` dollars by its real cost."""
        with self._lock:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            with self.costs.open("a") as f:
                f.write(json.dumps(line) + "\n")
            self._all += line["dollars"]
            self._run += line["dollars"]
            self._reserved -= release
            if lines is not None:
                lines.append(line)

    def _reserve(self, worst):
        with self._lock:
            if (
                self.budget is not None
                and self._run + self._reserved + worst > self.budget
            ):
                raise BudgetExceeded(
                    f"run total ${self._run:.4f} + in flight ${self._reserved:.4f} + next call "
                    f"${worst:.4f} passes budget ${self.budget:.4f}"
                )
            if self._all + self._reserved + worst > self.ceiling:
                raise CeilingReached(
                    f"total ${self._all:.4f} + in flight ${self._reserved:.4f} + next call "
                    f"${worst:.4f} passes ceiling ${self.ceiling:.4f}"
                )
            self._reserved += worst

    def _release(self, worst):
        with self._lock:
            self._reserved -= worst

    def call(self, prompt, sample=0, prefix=None, lines=None):
        """prefix: the fixed, cacheable part of the prompt (rule and policy texts), sent as
        the provider's cached system block; prompt: the uncached user message. lines: a list
        that gets this call's own cost line. Stores the stop reason on `last_stop_reason`
        (a bound gate keeps its own)."""
        self.last_stop_reason = None
        text, stop = self._call(prompt, sample, prefix, lines)
        self.last_stop_reason = stop
        return text

    def _call(self, prompt, sample, prefix, lines):
        """(text, stop reason); safe to call from many threads."""
        start = time.monotonic()
        hit = self.cache.get(self.model, prompt, sample, prefix)
        if hit is not None:
            self._log(
                {
                    "model": self.model,
                    "input_tokens": hit["input_tokens"],
                    "cached_tokens": 0,
                    "output_tokens": hit["output_tokens"],
                    "dollars": 0.0,
                    "latency": time.monotonic() - start,
                    "cache": True,
                    # The model the provider named when the answer was cached; an entry
                    # cached before T34 has none.
                    "response_model": hit.get("response_model"),
                },
                lines,
            )
            return hit["text"], None
        prefixed = prefix is not None
        worst = dollars(
            self.price,
            project_tokens((prefix or "") + prompt),
            0,
            self.max_output,
            prefixed,
        )
        self._reserve(worst)
        logged = False
        try:
            attempt = 0
            while True:
                try:
                    text, n_in, n_cached, n_out, stop, served = _ask(
                        self.provider, self.model, prompt, self.max_output, prefix
                    )
                    break
                except Exception as exc:
                    wait = retry_wait(exc, attempt)
                    if wait is None:
                        raise
                    self.sleep(wait)
                    attempt += 1
            self._log(
                {
                    "model": self.model,
                    "input_tokens": n_in,
                    "cached_tokens": n_cached,
                    "output_tokens": n_out,
                    "dollars": dollars(self.price, n_in, n_cached, n_out, prefixed),
                    "latency": time.monotonic() - start,
                    "cache": False,
                    "response_model": served,
                },
                lines,
                release=worst,
            )
            logged = True
        finally:
            # The reservation is released on any exit; the log released it already.
            if not logged:
                self._release(worst)
        # An empty answer is never cached: the next run asks again.
        if text and text.strip():
            self.cache.put(
                self.model,
                prompt,
                sample,
                {
                    "text": text,
                    "input_tokens": n_in,
                    "output_tokens": n_out,
                    "response_model": served,
                },
                prefix,
            )
        return text, stop

    def for_sample(self, sample):
        return _Bound(self, sample)


class _Bound:
    """The gate as an agent sees it: the run's sample index is already fixed. It keeps its own
    cost lines and stop reason, so threads sharing the gate never mix them."""

    def __init__(self, gate, sample, cost_lines=None):
        self._gate, self.sample = gate, sample
        self.cost_lines = [] if cost_lines is None else cost_lines
        self.last_stop_reason = None

    @property
    def gate(self):
        """What an agent calls `for_sample` on (cheap_strong): a view whose bound gates
        record into this one's cost lines."""
        return _Scope(self._gate, self.cost_lines)

    def call(self, prompt, prefix=None):
        text, stop = self._gate._call(prompt, self.sample, prefix, self.cost_lines)
        self.last_stop_reason = stop
        return text


class _Scope:
    def __init__(self, gate, cost_lines):
        self._gate, self._lines = gate, cost_lines

    def for_sample(self, sample):
        return _Bound(self._gate, sample, self._lines)
