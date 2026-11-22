# The figures the README states

Hand-written. Each row is a figure that the README states and no other file of this folder
holds; the last two columns name what computes it and the test that checks it against the real
runs (`SAY_IT_TWICE_RUNS=<repo>/runs SAY_IT_TWICE_DATA_ROOT=<repo> uv run pytest -q -rs
tests/test_readme.py -k real`). The test reads the value of the second column of each row.

| Figure | Value | Computed by | Test |
|---|---|---|---|
| `plain_same` | 84% | `primary.H1.values.naive` of `runs/confirm/report.json` (`report.confirm`), the plain agent giving the same answer in all ten runs of a case | `test_real_figures_match` |
| `plain_same_cases` | 109 of 130 | the same figure as a count of cases: that share times 130 | `test_real_figures_match` |
| `code_same` | 100% | `primary.H1.values.system` of the same report, the same model with the rules in code | `test_real_figures_match` |
| `wrong_rule` | 21 of 130 | `eval.delays.flipped`: the cases whose label the delay reading of ADR-0008 changes to no refund | `test_real_figures_match` |
| `correct_fixed` | 103 of 130 | `eval.fixed_rule.analyze`, `correct`: cases correct in all ten runs with the rule fixed, against the ADR-0008 labels | `test_real_figures_match` |
| `handed_over` | 12 of 130 | `eval.fixed_rule.analyze`: cases whose ten decisions, with the rule fixed, all hand the case to a person | `test_real_figures_match` |
| `lacked_fact` | 2 cases | `eval.fixed_rule.analyze` against the registered decisions: cases the fix sends to a person because a fact is missing | `test_real_figures_match` |
| `lacked_fact_runs` | 20 runs | the same, counted in runs | `test_real_figures_match` |
