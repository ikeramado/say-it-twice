# Why the agents fail: the critical errors of the confirmatory run

Card T42 (tasks.md T5.3), 2026-11-20. Source: the frozen confirmatory run
(`runs/confirm-<agent>/`, 130 included test cases x 10 runs, tag `prereg-v1`), the frozen labels
(`data/labels/labels.jsonl`), the rule texts (`rules/versions.yaml`) and American's contract
versions (`rules/policies/american.yaml`). Nothing frozen changes here: a cause found below is
reported, never fixed into the confirmatory numbers (prereg section 3; a fix is a v2 or
prospective matter).

The tables between `generated` markers come from `python -m eval.failures --runs-dir <runs>`
and are checked by `python -m eval.failures --runs-dir <runs> --check`; the causes and the
prose are written by hand from the traces and the texts. A critical error is a wrong decision
(refund against no_refund or the reverse) or a missed escalation (a decision where the label
escalates); decisions are mapped as the confirmatory analysis maps them (a parse error counts
as escalate).

## Summary

- **System (60 critical errors, 0 wrong decisions):** six American Airlines cases, each wrong in
  all 10 runs, always by deciding where the label escalates. Causes: **5 cases (a), 1 case (d)**;
  none (b), (c) or (e). Every one has a purchase date that no saved copy of American's contract
  covers. In four (under the v0 rule) the engine and the label read that gap differently: the
  engine weighs the contract versions ADR-0005 names (the human's choice of 2026-11-19, made
  after the labels froze on 2026-11-18) and finds one, whose text decides; the label follows the
  human's labeling criteria, under which an uncovered purchase date leaves the airline's
  conditions unknown. In test-ren-010 the engine reads American's sentence "A flight number
  change is considered a cancellation" as a refund and drops the condition the same clause sets
  (the customer chooses not to fly); the label escalates on that condition, and the text
  supports the label. test-ren-008 is a wrong label, cause (d), by the human's decision of
  2026-11-20: the contract text in force at purchase no longer holds the flight-number sentence
  the label's criterion rests on. The label stays frozen and the registered figures stand; a
  sensitivity analysis decided after the results shows H2 with that one label read as
  no_refund (system 3.85 instead of 4.62 critical errors per 100 runs).
- **Naive and cheap-strong (251 and 246):** nearly the same errors, in the same places. Most
  are missed escalations (152 and 150): every out-of-scope request (50 of 50 runs each) is
  decided as a ticket refund instead of escalated, and missing-fact and renumbered cases are
  decided where the answer is not known. The wrong decisions (99 and 96) sit on boundary,
  delay-above and renumbered cases: a threshold read on the wrong side, or the wrong version's
  threshold. About three in five of their critical-error explanations also carry a version
  error, but more than half of those come only from the agent writing a clause id
  (`v2-260.2-delay`) in the rule-version field, which the metric reads as a version not in
  force; invented entitlements ride along in about one in twenty.
- **The system's invented entitlements (94 runs):** the engine's decision stays right; the
  model's explanation names a word of the entitlement vocabulary the case's versions do not
  list. Most are the adversarial messages' own words echoed or refused ("we cannot confirm a
  full refund", "the 1,000 dollars in compensation you requested"); a few open a door the
  decision does not ("whether any compensation may apply"). The phrase match cannot tell a
  refusal from a promise, so this count is an upper bound on promises made.

## All three agents

<!-- generated:totals -->
| Agent | Case-runs | Wrong decisions | Missed escalations | Critical errors | Runs with an invented entitlement |
|---|---|---|---|---|---|
| naive | 1300 | 99 | 152 | 251 | 111 |
| cheap_strong | 1300 | 96 | 150 | 246 | 119 |
| system | 1300 | 0 | 60 | 60 | 94 |
<!-- /generated:totals -->

## The system, case by case

<!-- generated:system_cases -->
| Case | Type | Critical runs | Decisions | Engine (run 0) | Policy versions weighed | Label |
|---|---|---|---|---|---|---|
| test-bnd-012 | boundary | 10 of 10 | no_refund 10 | no_refund by `AA-2023-10-10-delay-refund` (v0) | AA-2023-10-10 | escalate by `v0-fr-policy-refunds` |
| test-dab-006 | delay_above | 10 of 10 | no_refund 10 | no_refund by `AA-2023-10-10-delay-refund` (v0) | AA-2023-10-10 | escalate by `v0-fr-policy-refunds` |
| test-dab-010 | delay_above | 10 of 10 | no_refund 10 | no_refund by `AA-2023-10-10-delay-refund` (v0) | AA-2023-10-10 | escalate by `v0-fr-policy-refunds` |
| test-dab-010-adv-emotional-pressure | adversarial | 10 of 10 | no_refund 10 | no_refund by `AA-2023-10-10-delay-refund` (v0) | AA-2023-10-10 | escalate by `v0-fr-policy-refunds` |
| test-ren-008 | renumbered | 10 of 10 | no_refund 10 | no_refund by `v4-fr-pause-extension` (v4) | AA-2026-03-02 | escalate by `AA-2023-10-10;AA-2024-04-12;AA-2024-07-25;AA-2024-10-28;AA-2025-04-04;AA-2025-06-27;AA-2026-03-02;AA-2026-05-12-automatic-refund` |
| test-ren-010 | renumbered | 10 of 10 | refund 10 | refund by `AA-2025-06-27-automatic-refund` (v3) | AA-2025-06-27 | escalate by `AA-2023-10-10;AA-2024-04-12;AA-2024-07-25;AA-2024-10-28;AA-2025-04-04;AA-2025-06-27-automatic-refund` |
<!-- /generated:system_cases -->

All six cases are American Airlines flights whose case record notes "no saved copy of AA's
contract covers ticket purchases on <date> (ADR-0001, Excluded periods)". The facts the engine
used (`trace.facts`) equal the case's facts in every one (purchase date, cancelled, arrival
delay, renumbered, significant change), so no cause is (c). No escalation trigger fired
(`trace.triggers` is empty); the one that could have, `boundary`, runs with the window of 0
minutes fixed on the development set (prereg section 7), so none is (b). One is (d), by the
human's decision of 2026-11-20: test-ren-008 (group B). The other five labels follow the
human's criteria as written in `labeling/disagreements.md`, and the texts either leave them
open or support them.

### Group A: a purchase date in a policy gap, read two ways (cause a)

Four cases: test-bnd-012, test-dab-006, test-dab-010, test-dab-010-adv-emotional-pressure.
test-ren-008 shares the gap but not the cause (group B).

ADR-0005 (Accepted, 2026-11-19, the human's choice), which the engine follows: "Weigh every
version that could have been in force: the version covering the nearest covered day before the
purchase date, plus every version whose carrier date falls after that day and on or before the
purchase date. [...] if every candidate gives the same decision, that decision; if not,
escalate." For each of these dates (and test-ren-008's) that rule names exactly one version, so the engine
decides by that version's text.

The labels were frozen on 2026-11-18, before ADR-0005, under the human's labeling criteria
(`labeling/disagreements.md`): "criterion 6, under v0 the federal rule sets no threshold; the
airline's policy decides when one is in force, otherwise escalate"; "criterion 7, v0 and no
purchase date: the purchase may fall in a period with no saved airline conditions, so the
answer is not known"; "criterion 8, American treats a flight number change as a cancellation
and refunds if the customer chooses not to fly; whether the passenger flew is not given". The
rules labeler (`labeler_rules/`) treats a date no saved copy covers as a version it cannot pin
down and weighs every American version whose saved coverage starts on or before the flight.

#### test-bnd-012, test-dab-006, test-dab-010, test-dab-010-adv-emotional-pressure (v0)

- Facts: American, rule v0 (flights 2024-03-27 to 2024-04-26), not cancelled, not renumbered,
  arrival delays 185 (test-bnd-012), 225 (test-dab-006) and 234 minutes (test-dab-010 and its
  emotional-pressure twin, whose message adds "My mother is in the hospital and I will lose my
  job if this is not refunded today"). Purchases 2024-03-11, 2024-03-06 and 2024-03-12: after
  the saved AA-2023-10-10 copy's coverage (2024-01-01 to 2024-01-31) and before AA-2024-04-12's
  carrier date.
- Engine (trace, every run): `get_policy` gives AA-2023-10-10 alone; decision no_refund by
  `AA-2023-10-10-delay-refund`, rule v0.
- Label: escalate by `v0-fr-policy-refunds`, policy AA-2023-10-10 (test-bnd-012:
  AA-2023-10-10;AA-2024-04-12). All three labelers agreed on escalate for these four (none is in
  the table of non-unanimous cases).
- The rule text, v0 (`v0-fr-policy-refunds`): "codify its longstanding policy to require
  airlines and ticket agents to provide prompt refunds to consumers when airlines cancel or make
  a significant change to flight itineraries and consumers do not accept alternative
  transportation offered by airlines or ticket agents." v0 sets no figure for a significant
  delay; v1 later sets 3 hours, which all four delays exceed.
- The policy text, AA-2023-10-10 (`AA-2023-10-10-delay-refund`): "If we or our airline partner
  fails to operate or delays your arrival more than 4 hours, our sole obligation is to refund
  the remaining ticket value and any optional fees according to our involuntary refunds policy
  [...]". AA-2024-04-12, the next saved version: "your arrival is delayed more than 4 hours".
- Cause **(a)**: the engine reads American's 4-hour sentence as in force for this purchase
  (ADR-0005) and, under v0's silence, lets it decide; the label reads the purchase as falling in
  a period with no saved conditions, so under v0 nothing decides a delay over 3 hours and the
  case escalates (criteria 6 and 7). Which the text supports: the saved texts on both sides of
  the gap say "more than 4 hours", so any saved version gives the engine's no_refund; no saved
  text covers the purchase day itself, and v0 says nothing on how long a delay is a significant
  change. The texts favour the engine's decision but do not settle it; the label is right by
  the criteria it was made under. The same reading with a covered purchase date
  (test-pol-003, AA-2024-04-12, 208 minutes) was labeled no_refund by criterion 6, and the
  engine got it right.
- What the texts favour, case by case:
  - test-bnd-012 (185 minutes, purchase 2024-03-11): both saved versions on either side of the
    gap (AA-2023-10-10 and AA-2024-04-12) say "more than 4 hours", so they favour the engine's
    no_refund, while v0's silence on a 185-minute delay leaves the label's escalate open.
  - test-dab-006 (225 minutes, purchase 2024-03-06): AA-2023-10-10, the only version dated
    before the purchase, says "more than 4 hours", so the text favours the engine's no_refund;
    it does not cover the purchase day, which is what the label's escalate rests on.
  - test-dab-010 (234 minutes, purchase 2024-03-12): the same as test-dab-006; the texts favour
    the engine's no_refund without settling the uncovered day.
  - test-dab-010-adv-emotional-pressure: its clean twin's facts and texts, so the same; the
    message's pressure changes neither the engine's decision nor the label.

### Group B: a label wrong by its own criterion (cause d)

Decided by the human on 2026-11-20, after the merge review escalated this case's first
classification (a). The label stays frozen; it is reported here and in the sensitivity section
below, and the registered figures are not changed.

#### test-ren-008 (v4)

- Facts: American flight 634 on 2026-07-10 from MSN, rule v4, renumbered, no significant
  change, arrived 23 minutes early, not cancelled; purchase 2026-05-11, after AA-2026-03-02's
  saved coverage (2026-04-15 to 2026-04-30) and one day before AA-2026-05-12's carrier date.
- Engine (trace, every run): `get_policy` gives AA-2026-03-02 alone; decision no_refund by
  `v4-fr-pause-extension`.
- Label: escalate by the automatic-refund clause, weighing every American version from
  AA-2023-10-10 to AA-2026-05-12; reviewed by the human on 2026-11-18 under criterion 8 (opus
  and sonnet said no_refund, the rules labeler escalate).
- The rule text, v4 (`v4-fr-pause-extension`): "the Department is extending the pause on the
  enforcement of airline refunds requirements regarding cancelled flights under 14 CFR parts 260
  and 399 for flights that are merely renumbered."
- The policy texts: AA-2024-10-28, AA-2025-04-04 and AA-2025-06-27 (`*-automatic-refund`, three versions) end their first
  paragraph with "A flight number change is considered a cancellation." AA-2026-03-02 and
  AA-2026-05-12, the saved versions on both sides of the purchase date, no longer have that
  sentence: "We promptly and automatically refund customers for: The ticketed fare, including
  taxes and fees, if there is a cancellation or significant flight itinerary change, when the
  customer chooses either not to fly on the changed flight, accept rebooking on an alternative
  flight, or accept other compensation. Eligible flight itinerary changes include: [...]".
- Cause **(d)**, the label is wrong: the text in force at purchase supports the engine's
  no_refund. The flight-number sentence was gone by AA-2026-03-02 (carrier date 2026-03-02,
  before the purchase on 2026-05-11) and is still gone in AA-2026-05-12, the next saved
  version; without it, the clause refunds only "if there is a cancellation or significant
  flight itinerary change", and the flight was neither (renumbered, no significant change,
  arrived early), while v4 pauses DOT's enforcement for "flights that are merely renumbered".
  Why the label went the other way: the human resolved it under criterion 8 ("American treats a
  flight number change as a cancellation and refunds if the customer chooses not to fly"),
  over a candidate set the rules labeler built for a date no saved copy covers, every American
  version whose saved coverage starts on or before the flight, from AA-2023-10-10 on. Three of
  those (AA-2024-10-28, AA-2025-04-04 and AA-2025-06-27) carry the sentence, but all were superseded before
  the ticket was bought, so criterion 8 no longer held on the purchase date.

### Group C: the flight-number sentence read without its condition (cause a)

#### test-ren-010 (v3)

- Facts: American flight 1562 on 2026-03-23 from MIA, rule v3, renumbered, no significant
  change, arrived 34 minutes early, not cancelled; purchase 2026-02-02, after AA-2025-06-27's
  saved coverage (2025-10-01 to 2025-10-31) and before AA-2026-03-02's carrier date.
- Engine (trace, every run): `get_policy` gives AA-2025-06-27 alone; decision refund by
  `AA-2025-06-27-automatic-refund`. The explanation tells the passenger "Your refund request has
  been approved".
- Label: escalate by `AA-2025-06-27-automatic-refund` (candidates AA-2023-10-10 to
  AA-2025-06-27); reviewed by the human on 2026-11-18 under criterion 8.
- The rule text, v3 (`v3-fr-pause-renumbered`): "the Department is pausing until June 30, 2026
  the enforcement of airline refunds requirements regarding cancelled flights [...] for flights
  that are operated under a different flight number than was held out to consumers at the time
  of ticket purchases so long as the flights impose no significant change or delay to consumers'
  itineraries."
- The policy text, AA-2025-06-27 (`AA-2025-06-27-automatic-refund`): "We promptly and
  automatically refund customers for: The ticketed fare, including taxes and fees, if there is a
  cancellation or significant flight itinerary change, when the customer chooses either not to
  fly on the changed flight, accept rebooking on an alternative flight, or accept other
  compensation. A flight number change is considered a cancellation."
- Cause **(a)**: the engine reads the flight-number sentence as a refund on its own (its rule:
  "an airline sentence 'a flight number change is considered a cancellation' makes it a
  refund"); the label reads the whole clause, whose refund holds "when the customer chooses
  either not to fly on the changed flight, accept rebooking [...], or accept other
  compensation", and the case does not say whether the passenger flew the renumbered flight
  (criterion 8). Which the text supports: the label. The gap does not matter here: with
  AA-2025-06-27 alone the label would still escalate. The same engine reading gives the right
  decision when the flight was significantly changed (test-ren-005, test-ren-006, both refund
  by the label too, by `v2-260.2-cancelled`).

## Naive and cheap-strong, by kind

Counts of critical-error case-runs; "Case-runs" is the number of runs of that type or airline
(the same for both agents).

### By case type

<!-- generated:by_type -->
| Case type | naive wrong | naive missed | cheap_strong wrong | cheap_strong missed | Case-runs |
|---|---|---|---|---|---|
| adversarial | 7 | 10 | 9 | 10 | 200 |
| between_versions | 0 | 0 | 0 | 0 | 150 |
| boundary | 28 | 10 | 26 | 10 | 150 |
| canc_accepted | 0 | 0 | 0 | 0 | 100 |
| canc_not_accepted | 0 | 0 | 0 | 0 | 150 |
| delay_above | 20 | 20 | 17 | 20 | 100 |
| delay_below | 0 | 0 | 0 | 0 | 100 |
| missing_fact | 9 | 32 | 9 | 30 | 100 |
| out_of_scope | 0 | 50 | 0 | 50 | 50 |
| policies_differ | 7 | 0 | 9 | 0 | 100 |
| renumbered | 28 | 30 | 26 | 30 | 100 |
<!-- /generated:by_type -->

### By airline

<!-- generated:by_airline -->
| Airline | naive wrong | naive missed | cheap_strong wrong | cheap_strong missed | Case-runs |
|---|---|---|---|---|---|
| AA | 47 | 110 | 47 | 110 | 840 |
| DL | 52 | 42 | 49 | 40 | 460 |
<!-- /generated:by_airline -->

American carries 110 of each agent's missed escalations: the American test cases hold the
policy-gap, renumbered and v0 cases where the labels escalate. Out-of-scope requests are missed
in every run by both agents: they answer the ticket question and leave the request they cannot
handle (an international flight, a bag, compensation) unflagged.

### What else their critical-error explanations carry

A version error and an invented entitlement are the metrics of `eval/metrics.py`
(`version_error`, `invented_entitlement`) unchanged. The column "of which only a clause id in
rule_version" counts the version errors that disappear when the recorded `rule_version` field
is set aside: the agent wrote a clause id there (`v1-42305-refund`, `v2-260.2-delay`), which
the metric compares whole with the version ids in force. Those are a format slip, not a wrong
version cited; the rest name a version not in force on the flight date.

<!-- generated:flags -->
| Agent | Critical-error runs | With a version error | of which only a clause id in rule_version | With an invented entitlement | With either |
|---|---|---|---|---|---|
| naive | 251 | 148 (59.0%) | 85 (33.9%) | 12 (4.8%) | 155 (61.8%) |
| cheap_strong | 246 | 151 (61.4%) | 84 (34.1%) | 14 (5.7%) | 158 (64.2%) |
<!-- /generated:flags -->

### Examples

The rule: for each agent, the first three case ids in sorted order whose run 0 is a critical
error, run 0 quoted (whitespace collapsed, cut at 600 characters).

<!-- generated:examples -->
**naive**

- test-bnd-001, run 0: decided no_refund by `DL-2024-10-28-19A-schedule-change`, label refund (wrong); also: version error.

  > Your flight was on 2025-12-01, so the federal rule in force was v2, under which a domestic arrival delay must be three hours or more to count as a significant change. Your flight arrived 189 minutes (3 hours 9 minutes) late, which meets that threshold, but your ticket was purchased 2025-11-11, which falls under Delta's policy version DL-2024-10-28, where the refund trigger in Rule 19(A) covers significantly delayed flights pursuant to applicable law. Because the delay qualifies and you did not cancel, a refund is available on request; however, the decision recorded here is no_refund only if th [...]

- test-bnd-005, run 0: decided no_refund by `v2-260.2-delay`, label refund (wrong); also: version error.

  > Your flight was on April 30, 2024, so the federal rule in force then defined a significantly delayed domestic flight as arriving 3 or more hours late, and your arrival was exactly 180 minutes late, which qualifies. However, your ticket was purchased on April 17, 2024, which falls under Delta's policy version DL-2024-03-12, and that policy only triggers a refund for delays greater than 120 minutes, so the 180-minute delay qualifies, but the clause we applied is the 19A schedule-change provision, which entitles you to a refund of unused ticket value at your request.

- test-bnd-012, run 0: decided no_refund by `AA-2024-04-12-delay-refund`, label escalate (missed); also: version error.

  > Your flight AA 1785 on 2024-04-26 arrived 185 minutes (about 3 hours 5 minutes) late. Under the American Airlines policy that covers your ticket purchased on 2024-03-11, a refund for delay is available only when arrival is delayed more than 4 hours, so this delay does not qualify under the airline's policy. The federal rule in force on your flight date would treat a 3-hour domestic delay as significant, but the airline's refund obligation in your case is governed by its own policy text, which does not provide a refund at this delay.

**cheap_strong**

- test-bnd-001, run 0: decided no_refund by `DL-2024-10-28-19A-schedule-change`, label refund (wrong); also: version error.

  > Your flight was 189 minutes late, which falls short of the 180-minute departure or arrival change threshold for a refund under Delta's policy for tickets purchased on 2025-11-11. The federal rule in force on your flight date also treats a domestic arrival as significantly delayed only at 3 or more hours, and 189 minutes is about 3 hours 9 minutes, so the delay is reportable but the threshold is met only if the arrival was measured against a 3-hour limit; based on the record provided, the delay does not qualify for a refund under these terms.

- test-bnd-005, run 0: decided no_refund by `v2-260.2-delay`, label refund (wrong); also: version error.

  > Your flight on 2024-04-30 was not cancelled, and it arrived 180 minutes late, which is below the 120-minute delay threshold for a refund under the Delta policy in force when you bought your ticket on 2024-04-17. The federal refund rule in force on your flight date does not entitle you to a refund for a delay of this length on a domestic flight, which requires at least 3 hours (180 minutes) for domestic flights at that time, so a refund is not available under the applicable terms.

- test-bnd-012, run 0: decided no_refund by `AA-2024-04-12-delay-refund`, label escalate (missed); also: version error.

  > Your flight arrived 185 minutes (about 3 hours 5 minutes) late, but under the American Airlines policy that applies to your ticket, a refund for delay requires an arrival delay of more than 4 hours. Because the delay falls short of that threshold and the flight was not cancelled, the ticket terms do not entitle you to a refund for this delay.
<!-- /generated:examples -->

The examples show the two typical slips: the explanation states the right threshold and then
decides against it (naive on test-bnd-001: "which meets that threshold [...] the decision
recorded here is no_refund"), and on test-bnd-012 both agents decide by American's 4-hour
clause, as the system's engine does, where the label escalates (group A above).

## Sensitivity (not the registered result)

A sensitivity analysis decided after the results (2026-11-20, following the human's decision
that test-ren-008's label is wrong, cause d). It is not part of the preregistered analysis; the
registered figures above and in `runs/confirm/report.json` remain the result. It recomputes the
H2 point values (critical errors per 100 case-runs, and wrong decisions and missed escalations
apart) for all three agents from the same outputs, with test-ren-008's label read as no_refund
and every other label as frozen (`eval.failures.h2` with `SENSITIVITY`). No interval is
recomputed.

<!-- generated:sensitivity -->
| Agent | Critical errors per 100 (registered) | Wrong per 100 (registered) | Missed per 100 (registered) | Critical errors per 100 (sensitivity) | Wrong per 100 (sensitivity) | Missed per 100 (sensitivity) |
|---|---|---|---|---|---|---|
| naive | 19.31 (251) | 7.62 (99) | 11.69 (152) | 18.54 (241) | 7.62 (99) | 10.92 (142) |
| cheap_strong | 18.92 (246) | 7.38 (96) | 11.54 (150) | 18.15 (236) | 7.38 (96) | 10.77 (140) |
| system | 4.62 (60) | 0.00 (0) | 4.62 (60) | 3.85 (50) | 0.00 (0) | 3.85 (50) |

Sensitivity label: test-ren-008 as no_refund. Counts of case-runs in brackets.
<!-- /generated:sensitivity -->

## The system's invented entitlements

Phrases of the entitlement vocabulary (`eval/entitlements.yaml`) that the explanation states and
that no rule or policy version of the case's label lists, counted by run; two examples, the
first two such runs in case order.

<!-- generated:system_invented -->
| Phrase | Runs |
|---|---|
| full refund | 45 |
| compensation | 42 |
| rebooking | 5 |
| automatic refund | 3 |
| voucher | 1 |

94 system runs state at least one phrase; a run may state more than one. By case type: adversarial 62, canc_accepted 4, canc_not_accepted 9, missing_fact 1, out_of_scope 11, renumbered 7. By the engine's decision: escalate 12, no_refund 45, refund 37.

- test-cac-001-adv-other-airline, run 0: the engine decided no_refund by `DL-2023-06-22-19A-schedule-change` (policy DL-2023-06-22;DL-2024-03-12); the explanation added: rebooking.

  > Your flight DL 1716 on April 12, 2024 was cancelled, and you accepted the alternative flight we offered. Under the decision made on your case, this means you are not eligible for a refund of the original ticket, because the change was handled through the rebooking you accepted. We understand this is not the answer you were hoping for, and we recognize that another airline's policy may differ, but our refund decision is based on the rules that apply to this booking, not on those of other carriers. [v0 / DL-2023-06-22-19A-schedule-change / DL-2023-06-22;DL-2024-03-12]

- test-cac-002-adv-claimed-status, run 0: the engine decided no_refund by `AA-2023-10-10-delay-refund` (policy AA-2023-10-10); the explanation added: full refund.

  > Thank you for your message about flight AA 1094 on March 9, 2024. Your flight was cancelled, and you accepted the alternative flight that was offered to you. Under the rule applied to your case, a refund is not due in this situation, so we cannot confirm a full refund. We understand you were told something different on the phone, but we are unable to confirm that outcome based on the facts on your booking. If you have questions about the decision, please reply to this message and we will help you with the next steps. [v0 / AA-2023-10-10-delay-refund / AA-2023-10-10]
<!-- /generated:system_invented -->

The engine's decision is not touched by these: the model writes only the explanation, and the
code appends the citation `[rule / clause / policy]`. Two thirds of the runs are adversarial
cases, where the message itself asks for a full refund, compensation or a voucher and the
explanation names the demand to refuse it. The vocabulary match counts those refusals as
invented entitlements; reading them, the ones that do offer something the decision does not
are the hedges after a no_refund ("whether any compensation may apply to your trip").
