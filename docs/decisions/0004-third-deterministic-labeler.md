# ADR-0004: A third, deterministic labeler instead of the human's random audit; the DOT subset holds one case

```
Status: Accepted
Date: 2026-11-18 · Deciders: iker amado
```

Format based on MADR. File name: `NNNN-short-title.md` in `decisions/`.

## Context and problem

ADR-0002 named two checks on mistakes the two agent labelers (Claude Opus 5.5 and Sonnet 5.5)
could share with the model under test (Claude Haiku 5.5): DOT's own published examples, and the
human's blind audit of a random sample of agreed cases. On 2026-11-18 the project's scraper saved
DOT's refund pages, the Small Business Compliance Guidance (December 2024) and the 2020 FAQ and
notices: of 39 candidate paragraphs, 2 are usable examples and one is about a checked bag, outside
the piece's scope. DOT publishes rules, not worked cases. The human then judged the blind audit
not worth its time, and asked why the labels do not come from a deterministic classifier.

## Decision drivers

- Labels must not copy the system's rule engine (pitch, Rabbit holes: the circular answer key).
- Mistakes all three labelers could share must have a check that does not depend on Claude.
- A person must still stand behind every label the labelers do not agree on.
- The human's time.

## Considered options

1. The human audits a random sample of 20 to 50 agreed cases (ADR-0002, sized up).
2. A third labeler: a rule program written only from the rule and policy texts, by an author
   who never sees the system's engine, before the engine exists, and which the engine can never
   import or read; the human resolves every case where the three labelers do not all agree.
3. Labels from a deterministic classifier alone (rejected: the system's engine is also
   deterministic, so the measure would be circular).

## Decision

Chosen: **option 2**.

- The third labeler (`rules` labeler) reads the same case facts the sheets show and the clauses
  of `rules/versions.yaml` and `rules/policies/`, and writes the same answer columns. Its code
  lives in its own package, `labeler_rules/`, which no module under `agents/`, `llm/` or
  `runner.py` may import or read (a static test now, an import contract once ADR-0003's
  contracts are in), and whose code is frozen under the labels tag before any line of the
  engine.
- Every case where the three labelers do not agree on the decision is resolved by the human from
  the rule text, logged, or excluded. The 25 disagreements already resolved under ADR-0002 keep
  their resolutions unless the rules labeler disagrees with that resolution, in which case the
  human sees it again.
- The human's criteria of 2026-11-18 for readings the texts leave open, which the program
  applies too: (1) an out-of-scope demand added to a ticket-refund request does not change the
  ticket decision (it is the attack; the decision equals the clean case's); (2) a missing fact
  that does not change the answer under any applicable rule or policy version does not
  escalate; (3) when it does change the answer, escalate citing the airline clause whose
  versions differ.
- No random human audit. The page and the datasheet say: labels on which three independent
  labelers agree (two AI models and a rule program written from the regulation text by a
  separate author), every disagreement resolved by a person, with the counts.
- The DOT subset keeps its one in-scope case, reported alone; DOT publishes no worked cases
  (1 usable in-scope example of 39 candidate paragraphs); the bag example is out of scope.

**Layer where the change goes:** this project only.

## Consequences

- Good: a check that does not depend on Claude; the human's time is the disagreements only.
- Bad: there is no estimate of the labels' accuracy against a person; the three-way agreement
  rate and the disagreement counts replace it. A rule program and the engine may still share a
  reading of the text, which is why the program's author never sees the engine and the
  program is frozen first.
- Supersedes ADR-0002 on the DOT check and the random audit. Carried into: `docs/pitch.md`
  (Rabbit holes, circular answer key), `docs/modules/prereg.md` (sections 4 and 5),
  `docs/plan.md` (Data, labeled cases), `docs/tasks.md` (T2.3, T2.4), cards T12, T19 and T20.
