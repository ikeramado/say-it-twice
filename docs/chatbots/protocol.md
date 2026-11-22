# Protocol: popular chatbots asked by hand

```
Status: Fixed before the first question (card T54, ADR-0006)
Date: 2026-11-20 · Decided by: iker amado
```

Descriptive and exploratory, outside the preregistration (`prereg-v1` is untouched). A small
sample, to be shown labeled "exploratory, small sample". No answer exists when this file is
committed; any change after the first answer is dated here and does not alter earlier answers.

## What is fixed (the human's decisions, 2026-11-20)

- **Chatbots (3):** ChatGPT, Gemini, Meta AI. File names: `chatgpt`, `gemini`, `meta-ai`.
- **Questions (4)**, in `questions.yaml` (`q1` to `q4`), each tied to a real BTS flight of
  Delta or American in `data/clean/flights/` and the rule version in force on its date
  (checked by `tests/test_chatbots.py`).
- **Repeats:** each question 3 times per chatbot: 4 x 3 x 3 = 36 answers.
- **Day:** all 36 asked on one single day, the three repeats the same day, each in a fresh
  conversation. The day is the date the human asks, on or after the commit of this protocol
  (not before 2026-11-20). It is recorded in the answer folder's date: one day, recorded in the
  answer folder's date.

## How to ask

1. Open the chatbot in a new private window, signed out where the service allows. A fresh
   conversation for every one of the 36 answers; never continue a conversation.
2. Paste the question's `text` from `questions.yaml` exactly as it is, with no preface, no
   follow-up and no regeneration. One answer per conversation, the first one given.
3. Nothing is automated against any chatbot (their terms of use): the human types and saves
   by hand.
4. Note the chatbot's model or product name as the page shows it, in the `note` column of the
   sheet.

## How each answer is saved

Under `data/chatbots/<YYYY-MM-DD>/` in the main checkout (tracked by git, not ignored: the
answers stay uncommitted until card T55 commits them as they are), one folder for the day, with a fixed name per chatbot, question and repeat:

- `<chatbot>-<question>-<repeat>.txt`: the answer's text, copied whole;
- `<chatbot>-<question>-<repeat>.png`: a screenshot of the whole answer.

For example `meta-ai-q3-2.txt` and `meta-ai-q3-2.png`. Repeats are numbered 1 to 3.
`python -m eval.chatbots validate` lists every gap, one line each (a missing answer or
screenshot, an empty answer, a file the protocol does not name, a day folder off the protocol),
and exits 1 on any.

## How each answer is scored

The expected answer of each question is in `questions.yaml`: `expected_decision`, the engine's
decision (`agents.system.engine.decide`) on the stated facts under the rule version in force,
and `not_given`, the entitlements and amounts in `eval/entitlements.yaml` that the version does
not give.

- **Decision**, in the sheet's `decision` column, by the human: `right` if the answer says what
  the rule gives (a refund when `refund`, no refund when `no_refund`), `wrong` if it says the
  opposite, `none` if it gives no usable answer (refuses, asks for details, hedges between both).
- **Invented**, in the `invented_human` column, `yes` or `no`: the answer states an entitlement
  or amount the rule does not give (a phrase of `not_given`, or one of the same kind).

`python -m eval.chatbots propose` creates or updates `data/chatbots/scores.csv` (columns
chatbot, question, repeat, date, decision, invented_proposed, invented_human, note) with a
row per saved answer, and fills `invented_proposed` with the phrase match that
`eval/failures.py` uses (`invented_phrases`, case-insensitive). The human reads each answer,
confirms or overrides the proposal in `invented_human`, and fills `decision`. The totals use the
human's columns only: `python -m eval.chatbots totals` prints, per chatbot, `asked`, `right`,
`wrong`, `none`, `invented` and `dates`.

## Limits stated up front

36 answers on one day say how these tools answered then, not how they answer in general; they
change over time, and the page dates them. The questions state the facts in plain words; the
real passenger's ticket terms are not modelled.

## Changes after the first answer (2026-11-20)

The first text above is kept. After the first answers (ChatGPT, q1 to q4) the human decided:

- **Text only, no screenshot.** The screen could not hold the answers; the `.txt` is the
  answer. `validate` no longer asks for a `.png` and reports one as not an answer.
- **One repeat.** Each question is asked once per chatbot: 4 x 3 x 1 = 12 answers, not 36. The
  time to ask 36 was not there, and the sample is small and labeled as such either way.
- **More than one day.** The answers may be asked on several days, each dated by its folder,
  on or after 2026-11-20 (the orchestrator's reversible choice, so the human can finish another
  day). The same file in two folders is still a gap.

q4's expected answer also changed, by ADR-0008: the question says the passenger arrived late,
so the passenger flew, and the text of `v1-42305-refund` owes the refund only where the
passenger "chooses not to" fly the delayed flight. q4 expects `no_refund`
(`travelled: true` in `questions.yaml`); the engine reads no such fact and still says `refund`.
