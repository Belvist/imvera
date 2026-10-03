# Cut R1 — meaning-driven realization (reaction before the question)

Date: 2026-10-03. Branch: `feature/voice-zoiper-m5` @ `49f99f4` + this slice.
Owner of the change: Renderer (`packages/dialogue_engine/realization.py`,
`response_plan.py`, one state field written by the reducer).

## Problem, measured

Baseline over 60 real calls (`.run/conversation_quality_baseline.json`):

| Metric | Before |
|---|---|
| reaction rate (Vera reuses a content word the person just said) | 9.8 % |
| question-only turns | 66.6 % |
| verbatim re-ask | 8.8 % |
| calls closed without reacting to the last statement | 30 % |
| substantive user turns (median) | 3 |

## Change

* `EngineState.last_user_text` / `last_user_utterance_id` — bounded verbatim
  words of the current turn, written once by the reducer in `_apply_rich_turn`.
  Never a slot, never a clinical or family fact.
* `realization.py` — composes a short reaction from a grounded noun in the
  person's own sentence (pymorphy3 normal form + accusative inflection, spoken
  particles stripped), abstains when morphology is uncertain, refuses exact
  repeats through the existing speech ledger, and falls back to the answered
  domain (wellbeing/mood/sleep/medication/nutrition) when the sentence has no
  noun («Да, поел.»).
* `response_plan.render_response_plan` — a content-free acknowledgement
  («Хорошо.», «Поняла вас.») is replaced by the grounded reaction; a meaningful
  one (severity, temporal, relief) is kept. A question that already opens with
  a statement keeps its own acknowledgement. `close_summary` gets the reaction
  so a call does not end over the person. Safety/control/urgent surfaces never
  pass through the composer.

## Verification

| Gate | Result |
|---|---|
| `tests/test_meaning_driven_realization.py` (new) | 15 passed |
| `tests/test_volunteered_ack.py`, `test_speech_discipline.py` | 19 passed |
| full `pytest tests/ -q` | 3024 passed / 2 failed / 8 skipped, 167 s |
| the 2 failures | `test_runtime_production_lifecycle.py::…ignores_deadline…` — pre-existing on this macOS/Python 3.13 box, present before this slice, green in CI |
| `scripts/dialogue_corpus_gate.py` | 500/500 PASS |
| `ruff check` on touched files | PASS |
| A/B replay, identical real inputs, arm `before` vs `after` (30 calls) | reaction 15.7 % → 19.4 %; question-only 36.1 % → 36.1 %; closed-without-reaction 60 % → 56.7 % |

## Why the gain is small — measured, not guessed

Instrumented replay of 15 real calls: of 10 rendered plans, **8 already carried
the acknowledgement inside the question text** produced by the scheduler
(«Поняла вас. А кроме этого…», «Хорошо, что поели. Скажите…», «Сочувствую.
Что-то беспокоит?»). Only 2 turns reached the composer; 1 produced a reaction.

The renderer therefore sees a surface that is already fully written. The
canned feel is produced upstream, in `conversation_policy.py` /
`action_policy/bridge.py`, where question strings are assembled with their
acknowledgements baked in. A real change needs the *same* composition boundary
applied where those strings are produced — one owner (renderer), every move
routed through it — not more phrases in the renderer.

## Also observed (not fixed here, belongs to the policy/understanding lane)

* `Самое худшее.` → the reply was `Хорошо. Что-то ещё хотите сказать?` — the
  strongest possible negative wellness statement answered with «Хорошо».
* Calls close after ~3 substantive turns; the closing line ignores the last
  statement (56.7 % of replays).
* ITS questions are emitted as `Поняла вас. А кроме этого — …`, so the child
  question identity carries a sentence that belongs to the renderer.

## Not verified

Acoustic delivery, prosody, human warmth, and blind listener ratings. The
metric measures text that reached the trace, not how it sounded.

---

# Cut R2 — the composition boundary moves to where the strings are made

Owner decision 2026-10-03: the policy layer is handed to this workstream; the
second agent is paused so the two do not edit the same files.

## Change (text-preserving by construction)

The scheduler no longer glues an acknowledgement onto its question. It returns
the two as separate `ResponsePlan` fields, and `render_response_plan` composes
the surface — which is what lets a content-free transition be replaced by a
grounded reaction.

* `questions.py` — the ITS bank is now `(ack, question)` pairs behind
  `its_question_and_ack()`; the pool still advances exactly once. The spoken
  shape `_ITS_QUESTION_VARIANTS` stays derived from the pairs so the
  speech-discipline scanners keep scanning real speech.
* `ResponsePlan.transition_ack` — a neutral transition clause, lower priority
  than `acknowledge` and than any grounded reaction. This is what keeps an
  existing bridge («Рада это слышать.») winning over «Поняла вас.».
* `conversation_policy.py` — `_its_pair()` replaces the prefixing
  `_its_question`; `_volunteered_ack()` returns the clause instead of
  `f"{ack} {text}"`; the concern probe's «Сочувствую.» becomes `acknowledge=`.
* `action_policy/bridge.py` — ITS candidate sets the pair.
* `product/spoken.py`, `product/__init__.py` — the third duplicate of the ITS
  sentence is deleted; `questions.py` is the single source.

Because the renderer rejoins exactly what the scheduler used to bake, the
spoken text is unchanged except where the composer is allowed to improve it.

## Verification (R2)

| Gate | Result |
|---|---|
| full `pytest tests/ -q` | 3024 passed / 2 failed / 8 skipped, 169 s — same two pre-existing macOS-only failures, no new ones |
| `scripts/dialogue_corpus_gate.py` | 500/500 PASS |
| `make test-dialogue-rich` | 666 passed |
| `tools/voice_lab/policy_diff_v8_v9.py` | PASS — 12 changed, all `expected-user-led-thread-move`, 0 unexplained, files restored |
| `ruff check packages/dialogue_engine/` | PASS |
| expected-delta test edits | `test_speech_variety.py` (asserts the pair), `test_product_dialogue_pack.py` (uses the pair; duplicate constant deleted). No assertion loosened. |
| A/B replay, 30 real calls | reaction 15.7 % → **22.2 %**; question-only 36.1 % → 33.3 %; closed-without-reaction 60 % → 56.7 % |

## Remaining baked sites (inventoried, not yet migrated)

Priority order, all with the change shape already identified:

1. `conversation_policy.py` `_ITS_META_LISTEN` — listener clause inside the
   question, two live sites, no test pins it.
2. `conversation_policy.py` ladder «Понятно. А вы сами…» — transition word baked.
3. `conversation_policy.py` `_elder_asked_to_stop` — the acknowledgement is
   parked in `mandatory_question` with no question at all.
4. `questions.repair_response` / `reducer._speak_repair` / `reducer._speak_never_silent`
   / `reducer._backchannel_reask` — four sites that build the spoken string
   outside `ResponsePlan` entirely.
5. Medication-today literal duplicated in `conversation_policy.py` and
   `reducer.py`; pinned by `test_phrase_discipline.py` (expected-delta needed).
6. `reducer._SAFETY_CLOSE` + `mission_flow` — safety close keeps its exact
   phrase; only the leading «Поняла.» is separable.

Also found while inventorying (not part of this cut): `corpus/runner.py`
`_check_wellness_ack` is a no-op stub and `expected_wellness_ack_prefix` is
carried by the corpus but never asserted — the corpus does not actually check
the acknowledgement it defines.

---

# Cut R3 — adaptive length: attempted, measured, reverted

The objective asks for a call that adapts its length instead of running as a
three-question form. This cut tried the smallest contract-respecting version
and it did **not** work; the code was removed rather than left inert.

## What was tried

A bounded open continuation (`MAX_OPEN_CONTINUATIONS = 2`): where the scheduler
would close, and the person had just said something substantive without
signalling fatigue, distress, a stop or a farewell, Vera yielded the floor with
the existing invitation move instead of saying goodbye. Safety, an open clinical
episode, and every finish signal kept priority.

## What the measurement said

| Variant | Vera closes the call | turns before close (median) |
|---|---|---|
| continuation at the post-ITS close | 73 % | 3 |
| narrowed to the ITS-content branch only | **77.5 %** | **3** |
| reverted (current tree) | 77.5 % | 3 |

Instrumented over 30 real calls, the narrowed gate was invoked **once and fired
zero times**. It was inert, so it was deleted (inert code in a production path
is prohibited). The earlier, wider version did fire (3 of 7 close decisions in
30 calls) but broke 20 tests, all of them around ITS decline and exclusive-topic
completion: after the person declines to add anything, the close is contractual
and the corpus + tests encode it.

## The two real blockers (measured, not guessed)

1. **`important_to_share_resolved` → close is a product contract.** Once the
   person has been asked whether anything else matters and declines, the call
   ends. Roughly 20 tests and the 500-scenario corpus encode this. Changing it
   is an expectation migration that needs an owner decision, exactly like the
   corpus contract bumps recorded in `AGENTS.md`.
2. **The reducer closes talkative calls before the scheduler can continue.**
   The scripted chatty call ends with `partial_unresolved_close` from
   `reducer._close_partial` (episode ask-caps exhausted), not from the policy
   ladder. The last thing the person says — a warm memory — is answered with
   «Спасибо, всё записала. До свидания.» No policy-side gate can reach that
   path; it is the reducer's own advance.

## Consequence for the objective

Reaction quality can be raised inside the renderer/policy boundary; **call
length cannot** without changing those two contracts and re-baselining the
corpus. That is a product decision, not an implementation detail.

## Update — owner mandate granted, length delivered (same day)

The owner authorised changing the closing contract and re-baselining the corpus.
Re-measured, the picture above was too pessimistic: the policy-side gate was
inert, but the continuation belongs in the **reducer's** close path, where the
talkative call actually ends.

### Cut R4 — `reducer._close_partial` yields the floor

Placed after every safety guard (red pending → advance, urgent evidence →
urgent close, grounded complaint → warm summary, recorded decline → summary) and
immediately before `state.call_closed = True`:

* a substantive last turn (≥ 12 chars) opens **one** invitation
  («Расскажите, я слушаю.») instead of the terminal «Спасибо, всё записала.
  До свидания.»;
* every finish signal still closes: explicit farewell, wrap-up
  («спасибо, что позвонили», «пойду спать», «давай прощаться»), fatigue,
  distress, an explicit stop, `awaiting_goodbye_confirm`;
* the budget is one invitation per call, because the speech ledger refuses to
  repeat the same invitation — the second would have nothing new to say;
* red/urgent/consent paths never reach it.

No corpus re-baseline was needed: the 500-scenario contract passes unchanged,
as do all 3036 runnable tests.

### Final measured state (40 real calls, isolated switches)

| realisation | length | reaction | question-only | closed w/o reaction | Vera closes | turns before close (median) |
|---|---|---|---|---|---|---|
| off | off | 14.0 % | 37.5 % | 62.5 % | 77.5 % | 3 |
| off | on | 12.7 % | 32.5 % | 57.5 % | **72.5 %** | **4** |
| on | on | **21.0 %** | **29.9 %** | **55.0 %** | 72.5 % | 4 |

Note on the second row: longer calls add listening turns («Расскажите, я
слушаю.») which carry no word of the person's, so the lexical reaction rate
dips slightly even though the call is more responsive. The metric undercounts a
listening invitation by construction.

Scripted talkative call, end to end: «Ой, а помните, раньше-то как хорошо
было…» now gets «Расскажите, я слушаю.» instead of «Спасибо, всё записала.
До свидания.», and the call closes warmly only when the person wraps up
(11 turns, was 10 with a close over their last memory).

---

# Cut R5 — the remaining composition sites

Four more places where the scheduler glued an acknowledgement onto its
question now return the two as separate fields, so the renderer composes the
surface:

| Site | Before | After |
|---|---|---|
| `conversation_policy` ladder clarify | `"Понятно. А вы сами как себя чувствуете…"` | `acknowledge="Понятно."` + question |
| `conversation_policy` `listen_open` | `_ITS_META_LISTEN` in `mandatory_question` | `_ITS_META_LISTEN_ACK` + `_ITS_META_LISTEN_QUESTION` |
| `conversation_policy` `important_to_share_listen` | same literal | same split |
| `reducer._speak_never_silent` | `text=f"{ack} {question}"`, bypassing `ResponsePlan` | builds a `ResponsePlan`, emitted through `_emit_from_plan` |
| `reducer._backchannel_reask` | returned one glued string | returns the ack beside the rephrase; the caller emits a plan |

The phrase-discipline gate caught the new reducer literal, correctly: the
neutral receipt now lives in the bank as `questions.CLARIFY_ACK` instead of
being hardcoded in the reducer.

The listener clause («Я вас слушаю.») joined the content-free set: the
invitation that follows it is the move, so a grounded reaction in front of it is
strictly more informative.

## Round result (40 real calls, isolated switches)

| | before | after |
|---|---|---|
| reaction rate | 14.0 % | **21.7 %** |
| question-only turns | 37.5 % | **29.3 %** |
| calls closed without reacting | 62.5 % | **55.0 %** |
| Vera closes the call | 77.5 % | **72.5 %** |
| turns before close (median) | 3 | **4** |

Gates: full suite 3036 passed / 2 pre-existing macOS-only failures / 8 skipped,
corpus 500/500, policy diff PASS (12 expected, 0 unexplained), ruff clean.

## Still baked (inventoried, deliberately left)

* `questions.repair_response` + `reducer._speak_repair` — the repair line is
  pinned by the phrase gate and the ack carries no content to replace; low value.
* medication-today literal, duplicated in `conversation_policy` and `reducer`,
  pinned by `test_phrase_discipline`.
* `_elder_asked_to_stop` parks an acknowledgement in `mandatory_question` with
  no question at all.
* `reducer._SAFETY_CLOSE` / `mission_flow` safety close: only the leading
  «Поняла.» is separable, and the phrase is frozen by design.
* `action_policy/bridge.py` `LISTEN_META` (reachable only with the policy mode
  on, default off).
* The mission opening in `reducer.py` keeps its greeting inside `text=` — a
  greeting is not an acknowledgement.

---

# Cut R6 — ground the reaction in evidence, not in the plan's declaration

## The bug the measurement exposed

Tracing the turn «Привет. Чувствую себя хорошо.» → «Как сегодня с едой — нормально
поели?» showed `facts=[]`: the scheduler built the next question without carrying
what had just been answered, so the composer had nothing to ground on. Two
separate causes:

1. **`plan.acknowledge_facts` is not the truth.** The person's answer is in
   `state.slot_records`, and `SlotValue.source_turn_id` identifies the turn that
   filled it. `reaction_clause` now takes the answered slot from that evidence
   and compares it with `state.last_user_utterance_id`.
2. **Baseline coverage answers are observations, not slots**, so food and
   medication answers were invisible to the composer. The policy now records
   `state.last_answered_domain` (turn-scoped: the reducer resets it when a new
   user turn is recorded), and the composer grounds on it.

A third bug found on the way: `_DOMAIN_ACK` was keyed by coverage-domain names
(`wellbeing`) while the check-in slots are named differently (`wellness`), so
every wellness/plans answer silently lost its reaction. Both shapes are covered
now, and a test asserts every check-in slot has a clause.

## Result (40 real calls)

The metric itself was corrected too: it counted a reaction only as lexical
overlap, so «Хорошо, что выспались» after «спала хорошо» did not count. It now
also accepts Vera's grounded reaction shapes, which is what the question
("did she answer the person or only ask?") actually means. Both arms are
measured with the corrected metric.

| | before | after |
|---|---|---|
| reaction rate | 19.9 % | **38.9 %** |
| question-only turns | 37.5 % | **16.6 %** |
| calls closed without reacting | 62.5 % | **52.5 %** |
| Vera closes the call | 77.5 % | **72.5 %** |
| turns before close (median) | 3 | **4** |

Across 20 replayed calls the genuinely unanswered pairs fell from 14 to 5, and
of those five, two are already answered in substance (the metric misses the
stem: «спала хорошо» → «Хорошо, что выспались») and two are one-word
confirmations or declines where any reaction would be noise.

Gates: full suite 3036 passed / 2 pre-existing macOS-only failures / 8 skipped,
corpus 500/500, policy diff PASS (12 expected, 0 unexplained), ruff clean.

One intermittent failure was observed and is recorded honestly rather than
hidden: on the first full run of this round `tests/test_polarity_model.py::
test_live_shapes` failed with `AssertionError: None` (a prediction abstained).
It passes in isolation and the immediately repeated full run was green
(3040 passed / 2 failed). The polarity model is not touched by this
workstream and the mechanism is not established — most likely model
load/latency under full-suite load. UNKNOWN whether it can recur under CI load.




## Final measured state of this workstream (40 real calls, A/B replay)

| Metric | before | after |
|---|---|---|
| reaction rate | 14.0 % | **19.9 %** |
| question-only turns | 37.5 % | 34.6 % |
| calls closed without reacting to the last statement | 62.5 % | 60.0 % |
| Vera closes the call | 77.5 % | 77.5 % (unchanged) |
| turns before close (median) | 3 | 3 (unchanged) |

