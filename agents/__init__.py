"""Agents: run(case, gate) -> {"decision", "explanation", "trace", ...}; gate.call(prompt) -> text.

Every agent reads a case only through agents.view.view(case)."""

from agents import cheap_strong, naive, placeholder
from agents.system import agent as system

AGENTS = {
    "placeholder": placeholder,
    "naive": naive,
    "cheap_strong": cheap_strong,
    "system": system,
}
