# Delay cases: the reading of the saved texts, as a sensitivity analysis

Card T58, 2026-11-20. Source: the frozen confirmatory run (`runs/confirm-<agent>/`), the frozen
labels (`data/labels/labels.jsonl`) and the rule texts (`rules/versions.yaml`). Nothing
registered changes here: the labels, the engine, the runs and the prereg stay as frozen. The
reading is ADR-0008 (`docs/decisions/0008-delay-refund-when-the-passenger-did-not-fly.md`,
Accepted by the human on 2026-11-20). This page is a sensitivity analysis decided after the
results, not the registered result.

## The reading

The saved texts owe the refund for a significantly delayed flight only to a passenger who
chooses not to fly it (49 U.S.C. 42305(a), 14 CFR 260.6(a), 260.1; quotes in the ADR). The
frozen labels and the engine read a domestic arrival delay of 3 hours or more as a refund even
when the passenger flew the flight. No test case carries a fact saying the passenger did not
fly; the fact that would keep a label is `travelled: false`.

## Which labels the reading flips

A label flips when it is `refund`, the case's facts say `cancelled: false`, no `renumbered:
true`, and no `travelled: false`: the refund then rests on the delay, whatever clause the label
cites.

<!-- generated:flipped -->
21 of the 130 included test cases, read as no_refund:

| Case type | Cases | Ids |
|---|---|---|
| adversarial | 4 | test-dab-001-adv-other-airline, test-dab-002-adv-claimed-status, test-dab-005-adv-emotional-pressure, test-dab-008-adv-out-of-scope |
| boundary | 5 | test-bnd-001, test-bnd-003, test-bnd-005, test-bnd-011, test-bnd-015 |
| delay_above | 8 | test-dab-001, test-dab-002, test-dab-003, test-dab-004, test-dab-005, test-dab-007, test-dab-008, test-dab-009 |
| missing_fact | 2 | test-mis-002, test-mis-007 |
| policies_differ | 2 | test-pol-002, test-pol-010 |
<!-- /generated:flipped -->

## Per agent, per 100 runs

<!-- generated:figures -->
| Agent | Wrong per 100 (registered) | Wrong per 100 (flipped) | Missed per 100 (registered) | Missed per 100 (flipped) | Critical per 100 (registered) | Critical per 100 (flipped) |
|---|---|---|---|---|---|---|
| naive | 7.62 (99) | 6.92 (90) | 11.69 (152) | 11.69 (152) | 19.31 (251) | 18.62 (242) |
| cheap_strong | 7.38 (96) | 6.62 (86) | 11.54 (150) | 11.54 (150) | 18.92 (246) | 18.15 (236) |
| system | 0.00 (0) | 16.15 (210) | 4.62 (60) | 4.62 (60) | 4.62 (60) | 20.77 (270) |

Counts of case-runs in brackets.
<!-- /generated:figures -->

## H2, with the flipped labels

<!-- generated:h2 -->
| System minus | Difference (registered) | 95% interval (registered) | Difference (flipped) | 95% interval (flipped) | Meets the criterion (flipped) |
|---|---|---|---|---|---|
| cheap_strong | -14.31 | [-18.76, -9.62] | 2.62 | [-4.17, 8.31] | no |
| naive | -14.69 | [-18.97, -9.92] | 2.15 | [-4.45, 7.99] | no |

Intervals: paired cluster bootstrap, seed 20261118, 10,000 resamples, as registered. H2 is met when every interval lies entirely below 0. Verdict, registered: confirmed; flipped: not confirmed.
<!-- /generated:h2 -->
