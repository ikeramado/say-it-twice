# The delay rule fixed to the law's words, the 130 cases decided again

Card T64, 2026-11-21. Exploratory: a fix made after seeing the test results, to be checked on
new cases (the monthly prospective set, S6). Nothing registered changes: the registered engine,
the labels, the runs and the prereg stay as frozen. The reading is ADR-0008
(`docs/decisions/0008-delay-refund-when-the-passenger-did-not-fly.md`).

## The corrected reading

For a significant delay the rule gives the refund only when the passenger did not fly: a fact
`travelled: false`. No test case carries it, so under the federal rule a delay gives no refund.
An airline's own contract may still give more, and is read as the engine reads it (its own
delay threshold). Only the engine's delay path is replaced (`eval/fixed_rule.py`); candidate
weighing and every escalation stay as registered, so the two missing-fact cases still escalate.

## How it is decided again

Each of the system's 1,300 confirmatory runs is decided again from the facts in its trace (the
delay) and the case's own facts (`cancelled`, `renumbered`, `travelled`), with the rule and the
policy rebuilt from the trace's ids. A trigger that fired stays an escalation. No model call:
the decision is the engine's, not the model's. Correct is read against the labels as ADR-0008
reads them (`python -m eval.delays`).

## What it shows

The corrected reading changes 20 of the 1,300 runs: the 2 missing-fact cases whose registered
decision was refund now escalate (a delay refund that rested on the federal threshold cannot be
decided without knowing whether the passenger flew). Every other delay case is still a refund,
because the airline's own policy gives it at its own threshold (for example Delta's schedule
change clause for test-bnd-001). So against the ADR-0008 labels the cases correct in all ten
runs stay at the same figure as the registered engine's: those labels read the delay refund as
owed only by the federal rule and do not consult the airline contract, and the fix does not
change what the contracts give.

## Figures

<!-- generated:figures -->
| Reading | Cases with ten identical decisions | Cases correct in all ten runs |
|---|---|---|
| Registered, frozen labels | 130 of 130 | 124 of 130 |
| Registered, ADR-0008 labels | 130 of 130 | 103 of 130 |
| Corrected, ADR-0008 labels | 130 of 130 | 103 of 130 |

ADR-0008 labels: the frozen labels, each refund that rests on a delay read as no_refund.
<!-- /generated:figures -->

## The ten decisions of each case

<!-- generated:cases -->
| Case | ADR-0008 label | Ten corrected decisions |
|---|---|---|
| test-bnd-001 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-bnd-002 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-bnd-003 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-bnd-004 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-bnd-005 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-bnd-006 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-bnd-007 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-bnd-008 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-bnd-009 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-bnd-010 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-bnd-011 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-bnd-012 | escalate | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-bnd-013 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-bnd-014 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-bnd-015 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-cac-001 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-001-adv-other-airline | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-002 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-002-adv-claimed-status | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-003 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-004 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-004-adv-claimed-status | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-005 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-005-adv-claimed-status | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-006 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-006-adv-ignore-rules | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-007 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-008 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-009 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cac-010 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-cna-001 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-002 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-003 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-004 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-005 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-005-adv-other-airline | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-006 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-006-adv-ignore-rules | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-007 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-007-adv-false-facts | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-008 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-009 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-010 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-011 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-012 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-013 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-014 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-014-adv-out-of-scope | refund | refund refund refund refund refund refund refund refund refund refund |
| test-cna-015 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-001 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-001-adv-other-airline | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-002 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-002-adv-claimed-status | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-003 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-004 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-005 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-005-adv-emotional-pressure | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-006 | escalate | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dab-007 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-008 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-008-adv-out-of-scope | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-009 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-dab-010 | escalate | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dab-010-adv-emotional-pressure | escalate | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-001 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-001-adv-false-facts | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-002 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-003 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-004 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-005 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-005-adv-false-facts | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-006 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-006-adv-out-of-scope | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-007 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-007-adv-false-facts | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-008 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-009 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-009-adv-emotional-pressure | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-010 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-dbe-010-adv-ignore-rules | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-mis-001 | escalate | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-mis-002 | no_refund | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-mis-003 | escalate | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-mis-004 | escalate | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-mis-005 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-mis-006 | escalate | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-mis-007 | no_refund | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-mis-008 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-mis-009 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-mis-010 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-oos-001 | escalate | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-oos-002 | escalate | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-oos-003 | escalate | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-oos-004 | escalate | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-oos-005 | escalate | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-pol-001 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-pol-002 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-pol-003 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-pol-004 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-pol-005 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-pol-006 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-pol-007 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-pol-008 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-pol-009 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-pol-010 | no_refund | refund refund refund refund refund refund refund refund refund refund |
| test-ren-001 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ren-002 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-ren-003 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-ren-004 | escalate | escalate escalate escalate escalate escalate escalate escalate escalate escalate escalate |
| test-ren-005 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-ren-006 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-ren-007 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ren-008 | escalate | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ren-009 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ren-010 | escalate | refund refund refund refund refund refund refund refund refund refund |
| test-ver-001 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-002 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-003 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-004 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-005 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-006 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-007 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-008 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-009 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-010 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-011 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-012 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-013 | refund | refund refund refund refund refund refund refund refund refund refund |
| test-ver-014 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
| test-ver-015 | no_refund | no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund no_refund |
<!-- /generated:cases -->
