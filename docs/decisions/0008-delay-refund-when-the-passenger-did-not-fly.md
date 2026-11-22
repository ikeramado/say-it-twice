# ADR-0008: A delay is refunded when the passenger did not fly

```
Status: Accepted
Date: 2026-11-20 · Deciders: the human (acceptance); drafted by the T58 card worker
```

Format based on MADR. Card: T58. Nothing
registered changes with this ADR (`git diff prereg-v1 -- docs/modules/prereg.md` stays empty;
labels, engine and runs are untouched).

## Context and problem

A chatbot's answer to T54's q4 (2026-11-20) pointed out that the study's engine, its frozen
labels and its delay cases read a domestic arrival delay of 3 hours or more as a refund even
when the passenger flew the delayed flight (the cases' messages say "My flight ... arrived very
late. I want my money back."). The saved rule texts say otherwise. The question is what the
texts give, and what the study can then claim about delay cases.

## Decision drivers

- The saved texts decide, not the engine's docstring ("a delay is refunded when the arrival
  delay reaches the lowest threshold").
- No registered thing may change (prereg section 3): the finding is reported, never fixed into
  the confirmatory numbers.
- No case carries a fact saying the passenger did not fly.

## What the texts say

The texts are not ambiguous: in each, the refund for a delayed flight is owed to a passenger who
does not accept the delayed flight.

- 49 U.S.C. 42305(a) (rule version v1, `rules/sources/v1-plaw-118-63-faa-reauthorization-act.pdf`,
  138 Stat. 1188-1189; clause `v1-42305-refund` in `rules/versions.yaml`): the carrier "shall,
  upon request ..., provide a full refund ... for any cancelled flight or significantly delayed
  or changed flight where the passenger chooses not to-- (1) fly on the significantly delayed
  or changed flight or accept rebooking on an alternative flight; or (2) accept any voucher,
  credit, or other form of compensation offered ... pursuant to subsection (c)."
- 42305(d), clause `v1-42305-delay-definition` (same file): a "significantly delayed or changed
  flight" includes "a flight where the passenger arrives at a destination airport-- (1) in the
  case of a domestic flight, 3 or more hours after the original scheduled arrival time". It
  defines which delays are significant; it does not remove the condition of 42305(a).
- 14 CFR 260.1 (v2, `rules/sources/v2-fr-2024-07177-refunds-final-rule.pdf`): the
  purpose is to refund "airfare for a flight that is cancelled or had a significant change of
  flight itinerary where the consumer does not accept the change to the flight itinerary,
  alternative transportation, airline voucher or credit, or other compensation offered by the
  carrier."
- 14 CFR 260.2, clause `v2-260.2-delay` (same file): a significant change is one where "(B) The
  consumer is scheduled to arrive at the destination airport three hours or more for domestic
  itineraries ... later than the original scheduled arrival time".
- 14 CFR 260.6(a)-(b) (same file; the August 2024 amendment, `v2-fr-2024-17602-...pdf`, widens
  the section's title to "significantly delayed or changed" flights): refunds are "due to a
  consumer when the consumer's right to a refund is undisputed because a carrier cancels a
  flight or makes a significant change", each case in (b)(1) to (b)(6) turning on the consumer
  who "rejected a significantly changed flight", who "rejects the alternative transportation
  and compensation offered", or who does not respond.
- The preamble (same file) says consumers "are entitled to a refund if they do not accept the
  change, or any alternative transportation offered", for the three- and six-hour delay.

The v3 and v4 texts (`v3-fr-2025-22140-...pdf`, `v4-fr-2026-13675-...pdf`) pause enforcement for
renumbered flights only and leave this unchanged.

The eCFR copy of Part 260 as amended (`rules/sources/v2-ecfr-part-260-versions.json`) holds the
version history only, not the text; the v2 quotes are the saved Federal Register text.

## Considered options

1. Keep the study's delay reading and say nothing.
2. Change the labels and the engine to the reading the texts give.
3. Keep every registered thing, state the reading, and report a sensitivity analysis.

## Decision

Chosen: **3**, because the registration is frozen (prereg section 3) and the texts are clear.
This ADR states the reading, and `python -m eval.delays` (output in `docs/results/delays.md`)
computes, from the frozen runs and labels, a sensitivity analysis decided after the results.

## Which case types and labels it touches

A frozen label flips in the sensitivity analysis when it is `refund`, the facts say
`cancelled: false` with no `renumbered: true`, and no fact says `travelled: false` (the fact
that would keep it; no case has it, and T59's chatbot protocol uses the same key). The refund
then rests on the delay, whatever clause the label cites (`v2-260.2-delay`,
`v1-42305-delay-definition`, `v1-42305-refund`, `v0-fr-policy-refunds`, an airline delay
clause). 21 included test cases flip: delay_above 8, boundary 5, adversarial 4 (copies of
delay cases), missing_fact 2, policies_differ 2; the list is in `docs/results/delays.md`.
Cancellation labels (`cancelled: true`), renumbered cases and escalate labels do not flip.

## What the study can and cannot claim

- It can claim what is registered: against the frozen labels, H2 is confirmed (system minus
  naive -14.69 [-18.97, -9.92]; minus cheap_strong -14.31 [-18.76, -9.62] critical errors per
  100 runs).
- It cannot claim that its delay labels are what the saved texts give for a passenger who flew:
  they read a delay as a refund with no sign that the passenger did not fly. Read as the
  texts give it, the system's wrong decisions and critical errors rise (16.15 and 20.77 per
  100 runs) and H2 is not met (differences 2.15 [-4.45, 7.99] and 2.62 [-4.17, 8.31]).
- It cannot claim to have measured the delay cases' refund decision for a passenger who did
  not fly: no case says so. T59 asks that of popular chatbots with an explicit fact.
- The site's eligible-flights figure stays an upper bound: a delayed passenger is owed the
  refund only if they did not fly.

## Consequences

- **Good:** the limitation is stated with figures beside the registered result, with no change
  to anything registered.
- **Bad:** the delay half of the registered cases tests a reading the texts do not give; a v2
  study would need cases with `travelled: false` and new labels.
- **Confirmation:** `python -m eval.delays --check` exits 0 on the committed document; the
  confirmatory report page and the site's limitations block carry the paragraph.

## Pros and cons of the options

### Keep the reading, say nothing
- Good: nothing to explain.
- Bad: the limitation stays hidden.

### Change labels and engine
- Good: labels match the texts.
- Bad: breaks the registration; the numbers would no longer be the confirmatory ones.

### Keep everything, report a sensitivity analysis
- Good: registration intact, the limitation visible with figures.
- Bad: the registered H2 and the flipped H2 disagree and both are shown.
