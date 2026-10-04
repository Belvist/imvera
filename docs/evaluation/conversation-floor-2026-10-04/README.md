# Conversation floor: reproduced live exchange and source correction

Target `feature/voice-zoiper-m5`. Baseline `0fc463c1a922fb40ecdb00979ac05b9ffe88bfc9`.
The peer's latest call report is [fs-145617fc](../../live-calls/fs-145617fc-vague-answers.md):
bridge `2d8315c`, five caller turns. Its initial “nothing to fix” verdict is incorrect.
No raw JSONL/audio or current deployed provider configuration is available here;
source diagnosis is based on independently reproduced canonical SDK behavior.

## First wrong decisions and owners

1. Shared fast semantic normalization drops `вроде`, but misses `вроде бы`.
   A heard wellness answer `Нормально вроде бы` consequently supplies no fact.
   Discourse then mistakes its length for substantive personal content.
2. Discourse `_listening_reply` replaces the person's story with each `Да` or
   `Нормально говорю`, resets willingness, and recognizes only a narrow finish set.
   The engine then repeatedly emits listening acknowledgments, with no progress.
3. The shared service-answer owner does not recognize requests for the next call
   move. `И что дальше?` incorrectly gets an external-knowledge abstention.
4. Renderer processes `answer_user_question` before semantic `next_slot`/need.
   Composing an answer with a selected next need consequently erases the question
   and sets `marks_question=False`. New navigation tests caught this during implementation.
5. Latest cleanup archived `scripts/prerender_opening.py`, still invoked by both
   `voice_up` and `freeswitch_voice_lab_env`. Full tests exposed import from an
   unrelated editable checkout; actual startup subprocess targets were missing.
   Restore the existing active file; keep other retired scripts archived.

## Keep / change / replacement

Keep one canonical understanding producer, EngineState, Reducer, DecisionRouter,
ActionPolicy, selected-question commitment and heard-playout lifecycle. No new
brain, FSM, scheduler, model worker, neural invocation or generative live layer.

Replace length-based promotion of grammatical feedback with floor-role checks
in existing discourse. Feedback retains the grounded story anchor; substantive
continuations still control the conversation for any number of turns. Explicit
completion gives the floor back without satisfying wellness or other goals.

Resolve bounded call navigation through the existing service answer owner.
The wrapper gives that resolved obligation to the same selector exactly once;
it preserves the original canonical turn/facts and composes its answer with the
chosen need. Safety/control/repair retain their owners. Questions with entities,
symptoms, medication or outside predicates cannot enter this navigation path.
Pure side questions continue to suspend the actual pending obligation.

Renderer realizes a selected semantic question first, then composes the answer.
A context-only slot is not permission to invent a question. Render retries retain
one answer, one question and the same question binding; phrase rotation advances
only on first realization. Canonical speech still goes directly to TTS.

## Actual before / after

[Before](before.json) is a clean detached baseline checkout;
[after](after.json) explicitly records the dirty implementation checkout.
Both bind imports to the intended source, pin the same flags/call IDs, run seven
complete sequences ten times (220 turns), and simulate audible completion.

| User | Before | After |
|---|---|---|
| Нормально вроде бы. | Расскажите, я слушаю. | Рада это слышать. Как сегодня с едой — нормально поели? |
| Story → И что дальше? | На этот вопрос у меня нет надёжного ответа. | Спасибо, что поделились. Можем продолжить. Я уточню то, чего вы ещё не рассказали. Самочувствие сегодня как? |
| Story → Я всё сказала. | Понимаю. | Спасибо, что поделились. Как себя чувствуете — всё нормально? |

These are source behavior corrections. The resulting short-call path still has
routine questions; it is not accepted as free human conversation. The personal
story path still has limited deterministic content realization. Fixing those
limitations requires the separate measured migration in ADR-028, rather than
claiming that this cut makes the system human.

## Checks and performance

- Initial regressions: **22 failed /5 passed**,0.50s before source changes.
- First implementation: **12 failed /15 passed**,0.50s, exposing renderer order.
- Focused existing lifecycle/answers/render tests: **157 passed**,1.46s.
- Initial broad rich run: **7 failed /709 passed**. Existing positive aliases
  were accidentally omitted; restored the original positive grammar. Two new
  tests incorrectly assumed phrase rotation was immutable; now verify only its
  expected first update and complete retry/state invariance. No original assertion changed.
- Final `make test-dialogue-rich`: **716 passed**,10.45s (37 new cases).
- Full local run: **3234 passed /3 failed /9 skipped**,147.38s before restoration
  of the active startup script. Two genuine relation-LFS readiness failures are
  inherited; the third reproduced peer cleanup and is fixed by restoring the file.
- Final startup/render/floor gate and exact remote CI results are recorded in `checks.json`.
- Synthetic SDK turn baseline p50 **1.747ms**,p95 **3.711ms**; after p50 **1.889ms**,
  p95 **3.730ms**,220 turns each, same managed Linux environment. This is neither
  end-of-speech latency nor target model throughput. No hardware capacity claim.

Commands:

```bash
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 make test-dialogue-rich PYTHON=/workspace/imvera-review-venv/bin/python
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 /workspace/imvera-review-venv/bin/python -m pytest -q
/workspace/imvera-review-venv/bin/python docs/evaluation/conversation-floor-2026-10-04/replay.py after.json
# For baseline: same command with --checkout /tmp/imvera-floor-baseline-0fc
```

## Not verified / remaining risks / next gate

NOT VERIFIED: actual deployed endpoints/flags, audio/prosody, latency and concurrent
model throughput. The report's engine p95 **4165ms** is unresolved; these fast-path
SDK measurements cannot explain or clear it. Provider model invocation count was
not measured by this replay; the source cut adds no generative model calls.

NEXT GATE: repeat the recorded vague exchange, substantive story with feedback,
explicit handoff and navigation through the actual CallActor/FreeSWITCH deployment;
retain audio + raw trace, exact SHA/providers/flags and every timing stage. Assess
questionnaire feel separately from factual correctness. The shared call-navigation
behavior is code-enabled in this branch; do not enable optional generation or
promote global medical ActionPolicy authority as part of integrating this cut.

## Voice-text follow-up and exact-source evidence

First published source `0f82c9e4ee7ef857c0357165ba585c24c1027209`,
[CI37167504976](https://github.com/Belvist/imvera/actions/runs/37167504976):
all11 jobs PASS; full3243 PASS/0 FAIL/3 SKIP,181.30s; rich716 PASS,17.14s;
runtime316 PASS,23.10s. Peer baseline CI37165552152 independently confirms
`ImportError: cannot import name 'prerender_opening' from 'scripts'`.

A further speech-form check found that plain STT `и что дальше` (no question
mark) still became a listening response. Twelve regression variants failed.
Late RichUserTurn recognition passed SDK tests but failed four real CallActor
admission/parity checks: fragment admission occurs before final understanding.
Move recognition into the existing `TurnUnderstandingV2.prepare_kernel`, which
already owns question recognition before admission. The admission filter is
unchanged. The original control/repair level-zero guard remains unchanged.
Pure request semantics now survive SDK and Actor, with one kernel preparation,
one mission attachment and one act proposal per controlled Actor utterance.
No new model inference is inserted, and candidate repair votes cannot override
this recognized question. Controlled ASR/act proposals are not neural accuracy.

Final local rich gate **732 PASS**,10.65s, including four additional Actor parity
cases and twelve unpunctuated exchanges. Runtime **316 PASS**,19.43s.
[Before voice-text replay](before-voice-text.json) and
[after voice-text replay](after-voice-text.json) contain eight complete exchanges,
240 turns each. Baseline `и что дальше` → `Понимаю`; after → answer + wellness
question with correct delivery binding. Original seven-case evidence is retained.
Exact final source **a15dc36096485fb47eecbd7f099eb2dafb800681**,
[CI37167925199](https://github.com/Belvist/imvera/actions/runs/37167925199):
**all11 jobs PASS**, full **3259 PASS/0 FAIL/3 SKIP**,176.67s;
rich732 PASS,15.97s; runtime316 PASS,22.73s. Genuine-model readiness is not
waived; both inherited local LFS failures pass in CI. This supersedes pending
publication status; actual deployment/audio/human acceptance remain NOT VERIFIED.
