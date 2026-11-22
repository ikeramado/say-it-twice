# ADR-0002: Two agent labelers, with the human resolving disagreements and auditing a sample

```
Status: Accepted
Superseded in part by ADR-0004 (audit, DOT check)
Date: 2026-11-18 · Deciders: iker amado
```

Format based on MADR. File name: `NNNN-short-title.md` in `decisions/`.

## Context and problem

The pitch (Rabbit holes, the circular answer key) and the prereg (section 5) name two labelers:
the author and an agent that never sees the code. With about 315 development and test cases at
one to two minutes each, the author's half costs 5 to 10 hours of a 3-week appetite. The human
judged that cost out of proportion on 2026-11-18.

## Decision drivers

- The answer key must stay independent of the rule engine (labels from the rule text, before
  the engine exists).
- A person must still stand behind the labels, with a number a reader can check.
- The appetite is 3 weeks and the human's time is the scarcest part of it.
- The agents under test are Claude models (Haiku 5.5): labelers from the same family could
  share their mistakes, which the measurement would then not see.

## Considered options

1. The author labels every case, as the pitch says (5 to 10 hours).
2. Two agent labelers of different models label every case; the human resolves every
   disagreement and audits a random sample of the agreed cases (about 1 hour).
3. One agent labeler, and the human audits a sample.

## Decision

Chosen: **option 2**, because it keeps two independent labelers and a person accountable for
the key, at about a tenth of the human's time.

- **Labelers:** Claude Opus 5.5 and Claude Sonnet 5.5, each a fresh agent dispatched by the
  orchestrator, each reading only its own label sheets (case and rule and policy texts in
  force; never code, never the other labeler's answers). Neither is the model of the agents
  under test. They run as Claude Code subagents, with no API cost.
- **Disagreements:** the human resolves each one from the rule text, or excludes the case; every
  resolution is logged.
- **Audit:** the human reviews 30 cases drawn at random (seed 20261118) from the cases both
  agents agreed on, without seeing the agents' answer first, then compares. The share where the
  human agrees with the agents is reported with its 95% interval. If it is below 90%, every
  agreed case of the failing case types is reviewed by the human before the labels freeze.
- **Shared-mistake risk:** the DOT guidance subset (labels by DOT, not by us) and the audit are
  the two checks on errors the labeler models and the tested model might share; agreement of
  each tested agent with the DOT subset is reported apart.
- **Declared:** the page and the datasheet state that the labels were set by two AI labelers
  from the official text, that a person resolved the disagreements and audited a random
  sample, and the audit's result (constitution, principle 18).

**Layer where the change goes:** this project only.

## Consequences

- Good: the human's labeling time drops from 5–10 hours to about 1 hour; two independent
  labelers remain, and kappa is still reported.
- Bad: a reader may trust AI labels less than a person's; the audit number and the DOT subset
  have to carry that trust.
- Carried into: `docs/pitch.md` (Rabbit holes, the circular answer key row),
  `docs/modules/prereg.md` (sections 3 and 5), `docs/plan.md` (Data, labeled cases),
  `docs/tasks.md` (T2.3, T2.4, T7.3), cards T11 and T12. The pitch, the plan and the tasks need
  the human's acceptance again.
