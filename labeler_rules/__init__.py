"""The rules labeler (ADR-0004): a rule program written from the rule and policy texts only.

It reads `rules/versions.yaml` and `rules/policies/*.yaml` as data, never `rules/lookup.py`
and never an engine. No module under `agents/`, `llm/` or `runner.py` may import or read it.
"""
