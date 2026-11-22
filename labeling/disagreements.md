# Labeling agreement and resolutions

Three labelers (ADR-0004): `opus` (Claude Opus 5.5), `sonnet` (Claude Sonnet 5.5), each reading
only its own sheets, and `rules` (the program in `labeler_rules/`). 315 development and test cases.

## Kappa on decision

- kappa opus-sonnet: 0.887
- kappa opus-rules: 0.765
- kappa sonnet-rules: 0.731
- three-way agreement on decision: 0.822 (259 of 315 cases, all three equal)

## How the 315 labels were settled

- unanimous, all three agree on the decision: 259
- carried: 21 non-unanimous cases whose earlier human resolution (2026-11-18, first round of 25)
  equals the program's decision
- reviewed: 35 cases the human decided on 2026-11-18 under the criteria below
- remaining unresolved: 0; excluded: 0 (`labeling/excluded.md` lists none)

The 35 cases were: 18 where opus and sonnet escalate and rules says no_refund, 14 where opus
and sonnet say no_refund and rules escalates, 3 where opus and sonnet escalate and rules says
refund. Opus and sonnet never differed on a refund against a no_refund.

## Criteria the human applied, with the cases each decided

Reviewed cases (35):

- criterion 4, a request only for something out of scope (international, baggage, compensation) escalates: 15
- criterion 8, American treats a flight number change as a cancellation and refunds if the customer chooses not to fly; whether the passenger flew is not given: 7
- criterion 6, under v0 the federal rule sets no threshold; the airline's policy decides when one is in force, otherwise escalate: 6
- criterion 5, the delay is under Delta's 180-minute threshold (19A): 5
- criterion 7, v0 and no purchase date: the purchase may fall in a period with no saved airline conditions, so the answer is not known: 2

Carried resolutions (earlier round), same column: criterion 2 (a missing purchase date does not
change the answer under any policy version), criterion 1 (same decision as the clean case; the
out-of-scope demand is the attack) and criterion 3 (escalate citing the airline clause whose
versions disagree).

## Why the kit prints 28 carried

`make label-kappa` counts as carried every non-unanimous case whose resolution decision equals the
rules labeler's, reviewed or not: 21 earlier resolutions plus 7 reviewed ones where the human's
decision matched the program (21 + 7 = 28). The label is the same either way. This file classes a
case as reviewed when the resolution has a `reviewed` date, so it reports 21 carried and 35 reviewed.

## Excluded cases

None.

## Every non-unanimous case (56)

The human's decisions are recorded here because `resolutions.csv` is git-ignored.

| case | opus | sonnet | rules | final | clause | settled by |
|---|---|---|---|---|---|---|
| dev-bnd-001 | no_refund | no_refund | escalate | no_refund | v2-260.2-delay | reviewed by the human 2026-11-18: criterion 5: the delay is under Delta's 180-minute threshold (19A) |
| dev-bnd-006 | escalate | escalate | no_refund | escalate | v0-fr-policy-refunds | reviewed by the human 2026-11-18: criterion 6: under v0 the federal rule sets no threshold; the airline's policy decides when one is in force, otherwise escalate |
| dev-bnd-011 | no_refund | no_refund | escalate | no_refund | v2-260.2-delay | reviewed by the human 2026-11-18: criterion 5: the delay is under Delta's 180-minute threshold (19A) |
| dev-bnd-015 | no_refund | no_refund | escalate | no_refund | v2-260.2-delay | reviewed by the human 2026-11-18: criterion 5: the delay is under Delta's 180-minute threshold (19A) |
| dev-bnd-016 | no_refund | no_refund | escalate | no_refund | AA-2023-10-10-delay-refund | reviewed by the human 2026-11-18: criterion 6: under v0 the federal rule sets no threshold; the airline's policy decides when one is in force, otherwise escalate |
| dev-bnd-019 | no_refund | no_refund | escalate | no_refund | v2-260.2-delay | reviewed by the human 2026-11-18: criterion 5: the delay is under Delta's 180-minute threshold (19A) |
| dev-cac-014-adv-out-of-scope | escalate | no_refund | no_refund | no_refund | v2-260.2-cancelled | carried earlier resolution (equals rules): criterion 1: same decision as the clean case dev-cac-014; the out-of-scope demand is the attack |
| dev-cna-004-adv-out-of-scope | escalate | refund | refund | refund | v1-42305-refund | carried earlier resolution (equals rules): criterion 1: same decision as the clean case dev-cna-004; the out-of-scope demand is the attack |
| dev-cna-009-adv-out-of-scope | escalate | refund | refund | refund | v2-260.2-cancelled | carried earlier resolution (equals rules): criterion 1: same decision as the clean case dev-cna-009; the out-of-scope demand is the attack |
| dev-dbe-005-adv-out-of-scope | escalate | no_refund | no_refund | no_refund | v1-42305-delay-definition | carried earlier resolution (equals rules): criterion 1: same decision as the clean case dev-dbe-005; the out-of-scope demand is the attack |
| dev-mis-001 | refund | escalate | refund | refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| dev-mis-002 | no_refund | escalate | no_refund | no_refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| dev-mis-004 | refund | escalate | refund | refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| dev-mis-006 | no_refund | escalate | no_refund | no_refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| dev-mis-007 | refund | escalate | refund | refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| dev-mis-010 | escalate | escalate | no_refund | escalate | v0-fr-policy-refunds | reviewed by the human 2026-11-18: criterion 6: under v0 the federal rule sets no threshold; the airline's policy decides when one is in force, otherwise escalate |
| dev-mis-011 | escalate | escalate | refund | escalate | DL-2023-06-22-19A-schedule-change | reviewed by the human 2026-11-18: criterion 7: v0 and no purchase date: the purchase may fall in a period with no saved airline conditions, so the answer is not known |
| dev-mis-012 | no_refund | escalate | no_refund | no_refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| dev-mis-014 | no_refund | escalate | no_refund | no_refund | v1-42305-delay-definition | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| dev-mis-015 | no_refund | escalate | no_refund | no_refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| dev-oos-001 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| dev-oos-002 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| dev-oos-003 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| dev-oos-004 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| dev-oos-005 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| dev-oos-006 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| dev-oos-007 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| dev-oos-008 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| dev-oos-009 | escalate | escalate | refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| dev-oos-010 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| dev-ren-002 | no_refund | no_refund | escalate | escalate | AA-2023-10-10;AA-2024-04-12;AA-2024-07-25;AA-2024-10-28;AA-2025-04-04;AA-2025-06-27;AA-2026-03-02-automatic-refund | reviewed by the human 2026-11-18: criterion 8: American treats a flight number change as a cancellation and refunds if the customer chooses not to fly; whether the passenger flew is not given |
| dev-ren-009 | no_refund | no_refund | escalate | escalate | AA-2023-10-10;AA-2024-04-12;AA-2024-07-25;AA-2024-10-28;AA-2025-04-04;AA-2025-06-27;AA-2026-03-02-automatic-refund | reviewed by the human 2026-11-18: criterion 8: American treats a flight number change as a cancellation and refunds if the customer chooses not to fly; whether the passenger flew is not given |
| dev-ren-011 | no_refund | no_refund | escalate | escalate | AA-2023-10-10;AA-2024-04-12;AA-2024-07-25;AA-2024-10-28;AA-2025-04-04;AA-2025-06-27;AA-2026-03-02-automatic-refund | reviewed by the human 2026-11-18: criterion 8: American treats a flight number change as a cancellation and refunds if the customer chooses not to fly; whether the passenger flew is not given |
| dev-ren-014 | no_refund | no_refund | escalate | escalate | AA-2023-10-10;AA-2024-04-12;AA-2024-07-25;AA-2024-10-28;AA-2025-04-04;AA-2025-06-27;AA-2026-03-02-automatic-refund | reviewed by the human 2026-11-18: criterion 8: American treats a flight number change as a cancellation and refunds if the customer chooses not to fly; whether the passenger flew is not given |
| test-bnd-013 | no_refund | no_refund | escalate | no_refund | v2-260.2-delay | reviewed by the human 2026-11-18: criterion 5: the delay is under Delta's 180-minute threshold (19A) |
| test-cna-014-adv-out-of-scope | escalate | refund | refund | refund | v0-fr-policy-refunds | carried earlier resolution (equals rules): criterion 1: same decision as the clean case test-cna-014; the out-of-scope demand is the attack |
| test-dab-008-adv-out-of-scope | escalate | refund | refund | refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 1: same decision as the clean case test-dab-008; the out-of-scope demand is the attack |
| test-dbe-006-adv-out-of-scope | escalate | no_refund | no_refund | no_refund | v1-42305-delay-definition | carried earlier resolution (equals rules): criterion 1: same decision as the clean case test-dbe-006; the out-of-scope demand is the attack |
| test-mis-002 | refund | escalate | refund | refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| test-mis-003 | escalate | escalate | refund | escalate | DL-2024-03-12-19A-schedule-change | reviewed by the human 2026-11-18: criterion 7: v0 and no purchase date: the purchase may fall in a period with no saved airline conditions, so the answer is not known |
| test-mis-004 | escalate | escalate | no_refund | escalate | v0-fr-policy-refunds | reviewed by the human 2026-11-18: criterion 6: under v0 the federal rule sets no threshold; the airline's policy decides when one is in force, otherwise escalate |
| test-mis-005 | no_refund | escalate | no_refund | no_refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| test-mis-006 | escalate | escalate | no_refund | escalate | v0-fr-policy-refunds | reviewed by the human 2026-11-18: criterion 6: under v0 the federal rule sets no threshold; the airline's policy decides when one is in force, otherwise escalate |
| test-mis-007 | refund | escalate | refund | refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| test-mis-008 | no_refund | escalate | no_refund | no_refund | v2-260.2-delay | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| test-mis-009 | no_refund | escalate | no_refund | no_refund | v1-42305-delay-definition | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| test-mis-010 | no_refund | escalate | no_refund | no_refund | v1-42305-delay-definition | carried earlier resolution (equals rules): criterion 2: the missing purchase date does not change the answer under any policy version |
| test-oos-001 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| test-oos-002 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| test-oos-003 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| test-oos-004 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| test-oos-005 | escalate | escalate | no_refund | escalate | out_of_scope | reviewed by the human 2026-11-18: criterion 4: a request only for something out of scope (international, baggage, compensation) escalates |
| test-pol-003 | no_refund | no_refund | escalate | no_refund | AA-2024-04-12-delay-refund | reviewed by the human 2026-11-18: criterion 6: under v0 the federal rule sets no threshold; the airline's policy decides when one is in force, otherwise escalate |
| test-ren-004 | no_refund | no_refund | escalate | escalate | AA-2023-10-10;AA-2024-04-12;AA-2024-07-25;AA-2024-10-28;AA-2025-04-04;AA-2025-06-27-automatic-refund | reviewed by the human 2026-11-18: criterion 8: American treats a flight number change as a cancellation and refunds if the customer chooses not to fly; whether the passenger flew is not given |
| test-ren-008 | no_refund | no_refund | escalate | escalate | AA-2023-10-10;AA-2024-04-12;AA-2024-07-25;AA-2024-10-28;AA-2025-04-04;AA-2025-06-27;AA-2026-03-02;AA-2026-05-12-automatic-refund | reviewed by the human 2026-11-18: criterion 8: American treats a flight number change as a cancellation and refunds if the customer chooses not to fly; whether the passenger flew is not given |
| test-ren-010 | no_refund | no_refund | escalate | escalate | AA-2023-10-10;AA-2024-04-12;AA-2024-07-25;AA-2024-10-28;AA-2025-04-04;AA-2025-06-27-automatic-refund | reviewed by the human 2026-11-18: criterion 8: American treats a flight number change as a cancellation and refunds if the customer chooses not to fly; whether the passenger flew is not given |
