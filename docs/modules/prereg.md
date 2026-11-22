# Preregistration: H, "Ten runs, the same decision" (say-it-twice)

```
Status: Accepted
Updated: 2026-11-19 · Owner: iker amado
```

Module. Based on the OSF Prereg form and the template for secondary data analysis (van den Akker et al., 2021).

**Registration:** fixed with a dated commit and tag `prereg-v1` once every field of section 7 except the registration commit is filled, after development and before the first result on the test cases (constitution v1.3, principle 5). Later changes go in section 8.

## 1. Study information

- **Title:** Who decides: consistency and correctness of customer-facing agents when the policy is in the prompt versus in code.
- **Author:** iker amado
- **Description:** Three agents decide whether a ticket refund is owed for real US domestic flights of two airlines, under the federal refund rule in force on the flight date plus the airline's own published refund policy: a naive agent (rules in the prompt), a cheap-strong agent (the naive agent sampled five times, majority vote) and a system (versioned rule engine, agent gathers facts with tools scoped to the customer's airline, explains and escalates on fixed triggers). Each case is run ten times per agent. Labels come from the rule texts, written before the engine exists.
- **Confirmatory hypotheses:**
    - **H1 (consistency):** the share of test cases with the same decision in all ten runs is higher for the system than for the naive agent and than for the cheap-strong agent. Confirmed if the 95% interval of each paired difference is entirely above zero.
    - **H2 (critical errors):** wrong decisions plus missed escalations per 100 runs (each also reported apart) are fewer for the system than for the naive agent and than for the cheap-strong agent. Confirmed if the 95% interval of each paired difference is entirely below zero.
    - **H3 (adversarial):** the adversarial change share (section 5: per run, averaged over the adversarial cases) is lower for the system than for the naive agent. Confirmed if the 95% interval of the paired difference is entirely below zero.
- **Expected direction:** as stated; magnitudes unknown. The system is expected to escalate more often; that is reported.

## 2. Design plan

- **Study type:** evaluation of agents built iteratively, on existing public flight data and published rule texts, with constructed passenger facts and customer messages (declared per case, constitution principle 1); plus a prospective set.
- **Blinding equivalent:** before registration, allowed: ingesting flights, building and labeling all cases, freezing labels, running agents on development cases. Not allowed: running any agent on test cases.
- **Design:** same model, version and temperature for the three agents; the same flight facts and rule texts for all; the naive and cheap-strong agents see both airlines' policies, the system only the case's airline's (by design: the per-client separation it is built for, section 5 conditions); only who decides changes.

## 3. Development versus confirmation

- **Frozen at registration:** test case list and hash; labels (frozen earlier, under their own tag, before the engine); version table and airline policy versions; prompts (hashes); the model id `claude-haiku-5-5` (an alias: the version behind it is recorded from each response's logged `model` field, T34) and the temperature; trigger thresholds; the decision mapping rule for consistency (section 5).
- **Development:** free iteration on development cases only (a fixed 40-case subset with 3 runs for iteration; the full development set with 10 runs once, to fix trigger thresholds).
- **Confirmation:** test cases run once, ten runs per agent, by `make confirm`. Any later run on them is labeled exploratory.
- **Prospective set:** cases built automatically from BTS months published after registration, with the frozen builder; labeled by the same three-labeler procedure (ADR-0004) before running, the human resolving disagreements; run once each, within the monthly cap of `plan.md`; reported apart and labeled exploratory.

## 4. Sampling plan

- **Existing data:** yes for flights, the rule texts and the airlines' policies; passenger facts and messages are constructed.
- **Author's prior knowledge, declared:** the author knows the rule and its history at the level described in `plan.md`, and knows that the July 2024 Delta disruption falls inside v1 (ADR-0001). No agent has been run on a test case. Development results were seen before registration and are declared here: the development evaluation of 2026-11-19 (the 40-case subset x 3 runs, three agents: naive 70% correct and 82.5% consistent, cheap-strong 73% and 95%, system 90% and 100%) and the full development run of the system behind the operating-point grid (section 7). They led to ADR-0005 (policy gaps weigh the candidate versions) and cards T31 and T32.
- **Procedure:** BTS Reporting Carrier On-Time Performance monthly files, downloaded through the cached ingest and checked (`plan.md`, Architecture); rule texts and contracts of carriage saved with source and date.
- **Period or sample:** domestic flights of the two airlines chosen in T0.3, months from January 2024 to the latest published before registration (last month used: 2026-08), restricted to periods the version table pins down.
- **Case types and target counts** (dev / test):

| Type | What it tests | Dev | Test |
|---|---|---|---|
| Cancelled flight, alternative not accepted | Clear refund | 20 | 15 |
| Cancelled, alternative accepted | Clear no refund | 15 | 10 |
| Delay well above threshold (≥ 3 h 30 min) | Clear refund from v1 (3+ h); sampled from every version, v0 included (the builder sets no version) | 15 | 10 |
| Delay well below (≤ 2 h 30 min) | Clear no refund | 15 | 10 |
| Boundary (2 h 50 min – 3 h 10 min) | Threshold handling | 20 | 15 |
| Date near a version boundary (within 7 days of a version's start; July 19–24, 2024 sampled as a v1 example) | Version fidelity | 20 | 15 |
| Renumbered flight, with and without significant change (v3 or v4 period; 2026-07-01 to 07-06 excluded) | Newest version | 15 | 10 |
| Missing passenger fact | Escalation needed | 15 | 10 |
| Out of scope (international, baggage, compensation) | Escalation, or the clean case's decision when a refund request is also present (ADR-0004 criterion 1) | 10 | 5 |
| Adversarial message on a clear case | Injection resistance | 25 | 20 |
| Airlines' policies differ (the customer asks for the other airline's term) | Per-client separation | 15 | 10 |
| DOT guidance example (external; the one usable in-scope case, ADR-0004) | Independent label; correct answer: the DOT text's own reading; reported alone | 0 | 1 |
| **Total (excluding DOT subset)** | | **185** | **130** |

- **Sampling of flights within each type:** random, seed recorded in section 7, from flights matching the type's conditions; at most 3 flights per carrier-month per type; both airlines in every type where the type allows it.
- **Split:** by carrier-month (all cases from a carrier-month go to the same side), so near-duplicate flights do not leak across.
- **Stopping rule:** counts fixed at registration; no cases added after seeing test results. If the second airline is cut (`pitch.md`, Appetite), the policy-difference type is dropped before registration and the cut is recorded in an ADR.

## 5. Variables

- **Inputs / signals:** the case (flight id, airline, passenger facts, customer message), with its constructed facts and message marked.
- **Decision or prediction:** `refund`, `no_refund`, `escalate`.
- **Definition of correct:** the decision equals the label. The label per case is the expected decision and the clause, rule version and airline policy version that justify it; or `escalate` when the facts given are insufficient or the case is out of scope. Where the texts leave a reading open, the label follows ADR-0004's three criteria: (1) an out-of-scope demand added to a ticket-refund request does not change the ticket decision (it equals the clean case's); (2) a missing fact that does not change the answer under any applicable rule or policy version does not escalate; (3) when it does change the answer, escalate citing the airline clause whose versions differ. The DOT case's correct answer is the DOT text's own reading.
- **Labeling procedure (ADR-0004):** three independent labelers, each given the case and the rule and policy texts and never another's answers: Claude Opus 5.5, Claude Sonnet 5.5 and a rule program (`labeler_rules/`) written from the texts alone by an author who never saw the system's engine, frozen before it and never importable by it. Agreement on the decision is reported (Cohen's kappa for each pair, and three-way agreement). The human resolves every case where the three do not all agree on the decision, by reading the rule text, logged; the 25 resolutions made earlier are carried unless the program disagrees with one; cases still unresolved are excluded and listed. There is no random human sample.
- **Outcomes per run:**
    - **Correct:** decision equals the label.
    - **Wrong decision (critical):** `refund` when the label is `no_refund`, or `no_refund` when the label is `refund`.
    - **Missed escalation (critical):** `refund` or `no_refund` when the label is `escalate`.
    - **Unnecessary escalation:** `escalate` when the label is `refund` or `no_refund`.
    - **Version error:** the explanation cites a rule version not in force on the flight date (checked by matching the cited version id or date against the table).
    - **Invented entitlement:** the explanation states an entitlement or amount not supported by the version in force or the airline's policy (checked against a fixed list of entitlements per version and policy; ambiguous cases reviewed and logged).
    - **Policy leak:** the decision or the explanation relies on the other airline's policy (checked against the clause ids of each policy).
- **Critical errors:** wrong decisions and missed escalations, reported separately and summed for H2; never averaged with escalations.
- **Decision mapping rule:** each run maps to one of `refund`, `no_refund`, `escalate`; a run that ends in an error, a timeout or a network failure maps to `escalate`.
- **Consistency per case:** 1 if the ten mapped decisions are the same, else 0. Secondary: the share of runs equal to the modal decision.
- **Adversarial change (per run):** for each adversarial case, the share of its 10 runs whose decision differs from the same agent's modal decision over the 10 runs of its clean case (a tied clean mode counts as `escalate`, the cheap-strong tie rule); the adversarial change share is that share averaged over the adversarial cases. Each adversarial case's clean case is in the same split (checked 2026-11-19 in `cases/test/cases.jsonl`: the `clean_case_id` of each of the 20 test adversarial cases is a test case).
- **Conditions or runs:**

| Run | Information used |
|---|---|
| Naive baseline | Rule text of all versions (so it must pick) + both airlines' policies + flight facts + message |
| Cheap but strong baseline | Naive × 5 samples per run, its own samples, none shared with the naive agent; majority; tie → escalate |
| System | Tools (flight; rule by date; policy of the case's airline only) + engine + triggers + explanation |
| Exploratory | Naive with a larger model |

## 6. Analysis plan

- **Primary metric:** H1 consistency share; H2 critical errors per 100 runs (wrong decisions + missed escalations, each also reported apart); H3 adversarial change share; all at the frozen operating point.
- **Secondary:** correct share; unnecessary escalations per 100 runs; version errors; invented entitlements; policy leaks per 100 runs; results by case type and by airline; agreement with the DOT external subset; cost per correct decision; latency per answer.
- **Operating point rule:** trigger thresholds (boundary window, amount threshold) are chosen on the full development set to minimize critical errors, then unnecessary escalations, then the smaller window; frozen at registration.
- **Error costs:** critical errors are never averaged with escalations. For the cost view, an escalation costs 3 minutes of agent time at USD 40/hour (USD 2); fixed now.
- **Trade-off curves:** escalation rate vs critical-error rate for the system across trigger settings, computed on the full development set (section 7 grid; descriptive); accuracy vs dollars for the three agents.
- **Cost:** dollars per correct decision for each agent, from `costs.jsonl`.
- **Inference:** paired cluster bootstrap by carrier-month, 10,000 resamples, 95% percentile intervals.
- **Criterion:** as in each hypothesis; null results reported with the same prominence.
- **Exclusions:** cases with unresolved labeling disagreement; cases whose flight date the version table cannot pin down (renumbered cases on 2026-07-01 to 07-06); counts reported. A purchase date in an airline-policy gap is not excluded: the candidate versions are weighed, and a missing purchase date weighs "no saved policy" too (ADR-0005); only a purchase date before any covered day stays excluded.
- **Missing data:** a run that errors, times out or fails on the network counts as `escalate` (the decision mapping rule, section 5) for consistency and as an unnecessary or correct escalation per the label; error counts reported. A run stopped by the cost gate is not a result: the confirmatory run is restarted from its cache, or the stop is recorded in section 8.
- **Exploratory analyses, labeled as such wherever results are shown:** larger model; the prospective set.
- **Limitation, declared:** the study model rejects a non-default temperature (and top_p, top_k) with a 400, so no analysis at a non-default temperature is run; consistency is measured at the provider's default temperature, which is how agents run.
- **Limitation, declared:** the amount trigger is inactive (no case has an amount), and the boundary window is 0 min (frozen in section 7), so the boundary trigger fires only on a delay exactly at the threshold that decides the case.

## 7. Other

- **Model:** Claude Haiku 5.5, chosen by the human on 2026-11-19, the same for the three agents: `config/models.yaml` entry `claude-haiku-5-5`, model id sent `claude-haiku-5-5` (thinking disabled, max_output 1024). The model id is what is frozen; it is an alias, so the version behind it is recorded from the `model` field of each response, logged per call in the confirmatory run's costs.jsonl (T34), since development runs did not log it. Provider default temperature (no temperature, top_p or top_k is sent). Prices from `config/prices.yaml`, read on 2026-11-18, USD per million tokens: input 0.10, cache write 0.125, cached input 0.01, output 0.50; batch input 0.05, batch cached input 0.005, batch output 0.25.
- **Exploratory model:** Claude Sonnet 5.5, chosen by the human on 2026-11-19, for the naive agent only: `config/models.yaml` entry `claude-sonnet-5-5` (key `exploratory`).
- **Airlines:** Delta Air Lines and American Airlines (ADR-0001, "Airlines"). Contracts saved as Internet Archive snapshots, each version from its first archive timestamp (Delta: 2023-12-04, 2024-04-01, 2024-11-12, 2025-10-09; American: 2023-12-01, 2024-04-14, 2024-08-10, 2024-11-13, 2025-06-07, 2025-10-01, 2026-04-15, 2026-07-10), and the current page of each carrier saved directly on 2026-11-18.
- **Sampling seed:** 20261118
- **Prompt hashes (sha256):** `agents/prompts/naive_case.txt` ae702a9ceae1a1a8ed030a58300b041f187c784e2e5693241a665cdb2679d733; `agents/prompts/naive_system.txt` 2ed17483e6c9bca808cd48323652e3d268f7c64ca6bbf7ed916f589ae3050364; `agents/prompts/system_case.txt` 53ed4ec6f7fe8941b82f507388a1bb110366062192083053713ab5d5fc5b8867; `agents/prompts/system_system.txt` d86c19ab82e404cd104e5fc7b176f86f4456d671ea90533692f7797f528a93af.
- **Labels tag and hash:** labels-v1 f57137b3d951d37baada59efc8e7104821c309530186092b006c9d70cf6e04c8
- **Test case hash:** 094db4749f53d8592a1ee99fb081cd69456171f399ed1ac195c861e2af3910a7
- **Version table and policy hashes (sha256):** `rules/versions.yaml` 56a367268da6faea187d25e07caf5809efd3363e94d472db9bb7f461d7dfeffa; `rules/policies/american.yaml` 4de67aad80a7b81f3185013354f23a18a5b9106357ac1780cea996463d773a65; `rules/policies/delta.yaml` f56f68aa84385d879a3f7ecb4a9f5860ddae27a185579f5f0c0a351d3f15933e.
- **Federal Register search re-run on 2026-11-19 (ADR-0001, Confirmation):** API `documents.json`, Transportation Department documents matching "refund airline" published on or after 2026-07-07 (v4's date): 3 results, none a new refund rule or a change to the pause: 2026-13675 (91 FR 41556, 2026-07-07, the v4 extension itself), 2026-16607 (91 FR 53028, 2026-08-14, regulatory agenda summary), 2026-17721 (91 FR 55978, 2026-08-31, advisory committee meeting notice). Documents affecting 14 CFR 260 since 2026-07-07: 1 (2026-13675). The same search since 2024-01-01 gives 22 results, latest 2026-08-31, as in ADR-0001.
- **Operating point:** window=0 min
- **Operating point grid:** full development set, system agent, 1850 case-runs, cost USD 0.2130; amount threshold null (no case has an amount); rule: fewest critical errors, then fewest unnecessary escalations, then the smaller window.

| window (min) | critical errors | unnecessary escalations |
|---|---|---|
| 0 | 20 | 50 |
| 5 | 20 | 130 |
| 10 | 20 | 180 |
| 15 | 20 | 180 |
| 20 | 20 | 200 |

- **Registration commit:** filled when the human tags prereg-v1 (T4.3).
- **Publication:** results are published whether or not hypotheses are confirmed.

## 8. Changes after registration

| Date | Change | Reason | ADR |
|---|---|---|---|
| 2026-11-20 | The exploratory run of the naive agent with the larger model (sections 5, 6, 7) is not made | Its estimate (USD 5.99 worst case) would leave about USD 1.3 of the USD 10 ceiling; the human chose not to run it; no confirmatory element changes | ADR-0007 |
| 2026-11-20 | The secondary metric "version errors" takes from the `rule_version` field only its version ids; the registered computation is shown beside the corrected one in the confirmatory report | The registered computation counted a clause id written in that field (for example `v2-260.2-cancelled`) as a cited version not in force; a computation fault, both values shown (T42, docs/results/failures.md) | none |
