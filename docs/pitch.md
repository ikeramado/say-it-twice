# Pitch: H, "Ten runs, the same decision" (say-it-twice)

```
Status: Accepted
Updated: 2026-11-19 · Owner: iker amado · Next review: 2026-11-19
```

One page. Decides whether this gets built and how much time it is worth. Written before `spec.md`; nothing is designed in detail here.

## Problem

Companies put AI agents in front of customers (support chat, WhatsApp sales, voice) and let them decide things that cost money: whether a refund is owed, what a package costs, when to hand over to a person. Two failures follow. The agent **invents** (a price, a policy, an entitlement) and the company is held to it; and the agent is **inconsistent**: the same case asked ten times gets different answers. Nobody measures either before going live.

## Why now

Agents moved from answering questions to taking actions with money attached. A tribunal already held an airline liable for what its chatbot said (Moffatt v. Air Canada, 2024 BCCRT 149: the airline argued the chatbot was responsible for its own actions; the tribunal rejected it and ordered it to pay the fare difference). Buyers now ask for agents that "never invent" and that escalate correctly.

## Evidence that someone wants this

| Evidence | Source | What it shows |
|---|---|---|
| WhatsApp CRM for a travel agency, $2,000 | Upwork, filtered sample of Nov 10 (`patrones-upwork-filtrado.md`) | "The AI captures the data and hands over to the salesperson; it never invents packages or prices" |
| Agentic workflow inside an existing process | Upwork, filtered sample of Nov 10 | "When to use AI and when plain logic" |
| Voice agent that escalates when needed; Shopify support chatbot with RAG ($500); multi-agent system ($30–60/h, client with $100K+) | Upwork AI & ML filtered, Nov 16 (`upwork-lectura-de-paginas.md`) | Agents that act, with escalation, are being bought now |
| Agent projects at $1K–10K | Upwork, filtered sample of Nov 10 | Budget range for pattern 3, "agent that acts without inventing" |
| Score 31/34 on the 17 questions | `preguntas-para-decidir-que-construir.md` | Tied for the highest score of the portfolio |

## Outcome for the user

The owner of a customer-facing agent sees, for cases like theirs: how often the agent gives the same decision across ten runs, how many decisions are wrong, how many it escalates and whether those escalations were needed, whether a customer can talk it out of the rules, and what each correct decision costs. They decide whether the agent can act alone, and on which cases.

## Appetite

- **Time budget:** 3 weeks for v1, measured from 2026-11-18. H is a standalone piece: it reuses no code from G and builds its own evaluation harness (runs, costs, bootstrap, report). Actual development time is logged per task in the time log of `tasks.md`, and the after-action compares it with the budget: H is a piece for applying to real offers, where delivery time is part of what a client buys, so the measured time is itself a result.
- **Why it is worth this much and no more:** H adds the agent harness (repeated runs, consistency, traces) that M and A reuse; the rule itself is small.
- **If the budget runs out:** the second airline goes first (one airline, per-client separation declared as a gap), then fewer case types and a static escalation tray; the test set and the measurement rules do not change. Scope is cut, not extended. Any cut or extension is an ADR.

## Solution, at rough level

1. Public twin: real US domestic flights from the Bureau of Transportation Statistics (scheduled and actual times, cancellations, cause codes) and the federal refund rule (14 CFR Part 260), with its versions by date.
2. Cases: a real flight + passenger facts (did they accept an alternative, when did they buy, was the flight renumbered) + a customer message, some of them adversarial.
3. Naive agent: the rule text in the prompt, flight data available, the model decides.
4. Cheap-strong agent: the naive agent sampled several times, majority vote.
5. System: the agent gathers facts with tools; a versioned rule engine computes the decision for the flight's date; the agent explains it citing the version and clause; fixed triggers send unclear cases to a person.
6. Two airlines, each with its own published refund policy on top of the federal rule (its contract of carriage), served by the same agent, as a travel agency serves several carriers: the agent must never apply one airline's policy to another airline's customer.
7. Every case run ten times per agent; consistency, correctness, escalation, adversarial resistance and cost measured on cases never used in development.

## Rabbit holes

Technical unknowns and design traps found before starting. Each one is either patched here or removed from scope.

| Rabbit hole | Patched how / or excluded |
|---|---|
| The rule changed several times (FAA Act of May 2024; Refund rule compliance Oct 28, 2024; enforcement pause for renumbered flights from Dec 5, 2025, extended in July 2026) and the July 2024 Delta meltdown falls inside v1, the statute (ADR-0001) | A version table with sources and effective dates is built and verified first (T0.3); cases are labeled by the version in force on the flight date. If a period cannot be pinned down from official text, cases from it are excluded and reported |
| BTS data has no passenger-level facts (alternative accepted, purchase date), and passengers' messages are not public | Passenger facts and customer messages are constructed per case and declared as constructed (constitution, principle 1); the flight facts are real. Declared on the page |
| BTS covers domestic flights of reporting carriers only | International cases (6-hour threshold) are a no-go for v1 |
| The answer key could just copy the rule engine (circular) | Labels are written from the regulation text before the engine exists, by three independent labelers: two agent labelers of different models (Claude Opus 5.5 and Sonnet 5.5, neither the model under test) and a rule program written from the text by an author who never sees the engine, which the engine can never import (ADR-0004); the author resolves every case where the three do not agree; agreement reported; DOT publishes no worked cases (1 usable in-scope example of 39 paragraphs), kept as a single held-out case |
| Renumbering is not visible in BTS | Renumbered cases are constructed on top of real flights and labeled as constructed |
| "Consistency" at temperature 0 looks perfect but is not how agents run | Runs use the provider's default temperature (fixed in prereg); the study model rejects a non-default temperature, so none is run, declared as a limitation |

## No-gos

- International flights and foreign carriers' rules (EU261 and others).
- Baggage-fee and ancillary refunds (same rule, different facts; v2 candidate).
- Compensation beyond refunds (meals, hotels): not required by the rule.
- A real messaging channel (WhatsApp, voice): the agent is exercised through a test harness and a demo page.
- A live form where visitors submit their own case: visitors are business owners, not passengers; the page's toggles and adversarial cases show the failure, and the visitor's own cases are the paid audit. v2 candidate.
- Legal advice: the page states it evaluates an agent, it does not tell anyone what they are owed.

## Hard questions

| Question | Answer |
|---|---|
| Isn't putting the rule in code "cheating"? The agent isn't deciding anymore | That is the finding the buyer pays for: decisions with money attached belong to code; the agent gathers, explains and escalates. The naive agent shows the cost of the alternative |
| Why would a WhatsApp travel-sales client care about airline refunds? | Same failure: an agent stating a price, a package or an entitlement that is not in the rules. The audit format is the same on their own cases |
| Synthetic passenger facts make it a toy | Flight facts, dates and the rule are real and checkable; passenger facts are declared and are the part a client supplies from their own system |
| What if the naive agent is already consistent? | Then it is published; the measured failures shift to wrong versions, invented entitlements and adversarial cases |
| Is this legal advice? | No. It evaluates agents against the published rule text, with sources; it remits to DOT for any individual case |

## Decision

- **Go / No-go / Later:** Go, conditional.
- **Date:** 2026-11-16
- **Conditions or first check before committing more time (≤1 day):** build the version table of the refund rule from official sources (Federal Register, DOT notices, the FAA Reauthorization Act of 2024) with exact effective dates, and confirm that BTS flight data can be downloaded for the months needed. If the version table cannot be pinned down, the case dates are restricted to periods where it can.
