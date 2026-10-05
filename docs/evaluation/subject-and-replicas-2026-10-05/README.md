# Собственные факты и распределение клиентов — 2026-10-05

Target **feature/voice-zoiper-m5**, baseline **0b87de7**. Source/CI/commands and
hashes: [checks.json](checks.json). Ordered work/resource model:
[plan and journal](../../dialogue-and-capacity-plan-2026-10-05.md).
No target deployment, new model/flag, generative speech or medical cutover.

## CHANGED

The existing routine fact owner now uses original mission clauses and existing
subject resolution for explicit mixed subjects; it preserves evidence offsets.
The mission wellness binder shares this boundary. Canonical contextual merging
cannot overwrite narrowed evidence or resurrect rejected foreign facts. Reducer
compatibility writes/first topic transition use own accepted source in mixed turns.
Non-mixed clinical compatibility and the plans tense/source owner are preserved.
The old mixed-text concatenation/whole-turn fallback was displaced, not supplemented
with a second interpreter/brain/state writer or more speech banks.

ReplicaPool shares only a locked rotation cursor among live clients with identical
ordered URLs in one process. Registry expires after the last pool disappears.
Final STT/TTS keep their existing failure/deadline/cancel/stream contracts; optional
STT prefix work rotates once without retry. This balances clients, not inference
inside a model. Two adapters sharing a Qwen resident still share one compute lane.

## Actual paired SDK exchange

USER: «Мне хорошо. Дочь плохо спала, а я выспалась.»

Before: «Понимаю, ночь была тяжёлая. Что-то ещё важное есть?» Both sleep and
wellness records contain the whole mixed story.

After: «Спасибо, что сказали, как спалось. Как сегодня с едой — нормально поели?»
Sleep source is exactly «а я выспалась.», wellness source «Мне хорошо».
No question about what disturbed the caller's sleep. Reverse quality still
acknowledges the caller's poor sleep. Daughter complaint is not recapped as own.

This fixes a factual mismatch; the after-example still contains a routine protocol
question. It is not evidence of unrestricted human conversation or a completed
coverage/policy migration. Plans retain their prior exact substring. Canonical
«Не могу дышать.» keeps urgent_close and RED candidate; explicit goodbye closes.

Full [before](before.json)/[after](after.json) and [cases](cases.json):12 cases,
380 text turns each, simulated heard completion. Replay [script](replay.py)
imports the requested checkout; after checkout is dirty baseline HEAD, code bound
by final hashes/checks. SDK p50/p95 before2.71/6.04ms, after2.52/7.29ms. Shared CPU
with a full suite, not isolated latency benchmark; no acceleration claim. No PCM,
STT/TTS/phone first audio or human rating measured. Total model invocations unmeasured.

## VERIFIED

- Same final17 regression tests: baseline16 FAIL/1 PASS/2.71s; changed source17 PASS.
- Final local suite3401 PASS/2 inherited relation-LFS readiness FAIL/9 SKIP/145.89s.
- Rich842 PASS/10.99s, runtime322 PASS/19.34s.
- Corpus500/500/5.53s plus8 gate tests; policy diff12 expected/0 unexplained.
- Repo Ruff and whitespace PASS.
- Controlled100 independent HttpSTT objects send actual adapter HTTP requests
  with100 distinct cancellation/request IDs and correct call/utterance identity:
  first replica50, second50. Threaded creation/selection and cursor expiry pass.
  Prefix503 makes one request, no retry. This is routing/contract proof only.

The first broad compatibility change caused15 regressions in existing clinical/
sleep/topic tests. Scope was corrected at the existing owners; all original
assertions remain unchanged. New test assumptions were corrected before acceptance:
sleep records can be unpolarized and clause punctuation/rotation varies; tests
require exact original ownership, absence of false reaction and proper next move.
Exact source GitHub CI with genuine LFS weights is recorded separately in checks.

## NOT VERIFIED / REMAINING RISKS

- Actual target SHA/image/profile/endpoints, whole-stack memory and speech latency.
-100 admitted phone calls and real model throughput under those calls. Resource
  arithmetic is a planning assumption, not a passed capacity gate. Admission1 unchanged.
- `ambiguous_continuation_open`: «Я чувствую себя хорошо. Дочь приехала. Плохо
  спала.» no longer fills a routine speaker sleep fact, but existing kernel/legacy
  mention handling still creates an own clinical sleep episode. Subject inheritance
  needs a coordinated kernel/merge ownership cut, including contrast and corrections.
- `urgent_synonym_open`: «Дочь плохо спала, а мне сейчас трудно дышать.» remains
  unrecognized as urgent in both source replays. This is a known semantic safety
  wording gap; canonical urgent tests do not prove coverage of arbitrary phrasing.
  Safety/control bytes were not changed in this cut. It blocks a product safety claim.
- Lexical coverage can count clinical blood sugar as nutrition; ordered plans,
  protocol minima and deterministic surface still affect questionnaire feel.

## NEXT GATE

Close the recorded kernel ownership/safety-wording/coverage counterexamples before
product acceptance. Then exact-revision CallActor/FreeSWITCH recordings with raw
STT, heard-question trace, stage p50/p95 and human warmth review; isolated10→25→50→100
model/SIP load soak with burst/failure/cancel recovery and measured memory.
