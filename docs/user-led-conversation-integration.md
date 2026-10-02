# User-led conversation: SDK / M5 integration handoff

2026-10-02. Target branch: `feature/voice-zoiper-m5`; main is not the source.
Design: [ADR-029](adr/029-user-led-conversation-moves.md).
Paired SDK evidence and gates: [Cut1b report](evaluation/user-led-conversation-cut1b-2026-10-02/README.md).
This is a source integration handoff, not a deployed-phone acceptance report.

## Ownership and actual live path

`audio → final STT → TurnUnderstandingV2.prepare_kernel → existing post-STT
admission → shared final resolve → RichUserTurn → Reducer → DecisionRouter →
existing ActionPolicy/legacy medical scheduler → ResponsePlan → renderer →
CallSession → CallActor → existing TTS/playback ledger`.

The Actor reuses its admitted kernel result. Do not interpret the same utterance
again or attach mission understanding before a dropped/held fragment is admitted.
SDK and Actor use the same grounding adjudication. Models propose meaning;
the reducer revalidates candidates against current authoritative context.
For an ordinary answered user question, complete its genuine non-question
playback through the same listening lifecycle. An active clinical episode,
pending/probe need or unprobed negative assessment blocks that floor, even if
the discourse label still says story after a reactive complaint.

Personal conversation now has one move selector: the existing ActionPolicy v10.
It chooses an invitation, listening ACK, or an actual needed mission return.
The displaced two-follow-up legacy branch was removed. There is no second FSM,
reducer, scheduler, LLM conversation owner, or transcript-sized model prompt.
Medical/custom mission authority remains under its existing routing flags.

`IMVERA_ACTION_POLICY_MODE=off` continues to mean legacy **medical** scheduling;
it does not disable the replacement personal-thread owner. Startup truth records
`action_policy.personal_thread_authority` and scope separately. Inspect actual
`decision_scope=personal_thread`, `policy_influenced_output`, chosen action and
router counters; a model proposal or global mode alone is not proof of use.
Selection/import/snapshot/bridge failure logs a scoped error and invokes the
existing obligations scheduler once. Failure to buffer telemetry does not undo
an already selected move. No alternate conversational brain is installed.

## Delivery contract

An invitation/ACK is genuine speech with `marks_question=False`. It must NOT
reserve/complete a health slot or increment a medical question attempt.

After its **actual current-generation PCM completion**, invoke the existing
`CallSession.mark_spoken_action(generation_id)` path. The reducer activates the
listening token and returns an existing `TimerEffect` with `listen:<token>`
scope. CallActor must consume that follow-up just as it consumes question waits.
Do not fire completion for cancelled/partial/stale playback or manufacture a
question ID to make listening work.

The current planned token and last **heard** listening origin are different.
An unheard/cancelled ACK or planned mission-return cannot turn “Хорошо” into a
health answer. The last heard context survives until a real new question is
completed or explicit clinical/control transition supersedes it. Historical
context never reactivates an old timer. The reducer also rejects stale cached
contextual health proposals for bare story evaluations; keep that validation.

An accepted explicit “Чувствую себя плохо” remains health evidence. A past
activity is not a future plan; a generic/hypothetical question is not a speaker
complaint. Unknown/refusal is not a fabricated clinical value. Terminal actual
goal/slot disposition overrides stale coverage when selecting a return point.
Frequency is a temporal modifier, not a symptom. A social clause and a separate
present complaint keep separate subjects, including punctuationless STT. The
existing planner accepts current status only with confirmed same-episode speaker
evidence, a source turn and quote; `active` by itself is not that proof.

## Before loading on M5

1. Save current loaded SHA/config/process versions and rollback reference;
   preserve local work, database and recordings. Fetch/fast-forward the target
   branch and hydrate actual trained LFS artifacts. Do not use main.
2. Install dependencies with the actual runtime Python and run the existing
   `make test-dialogue-rich`, `make test-dialogue-runtime`,
   `make test-semantic-kernel`, `make test-action-policy-shadow`,
   `make dialogue-corpus-gate`, full tests and lint. `all_hot` must be real.
3. Check exact source/model/endpoint/runtime flags. Drain active calls before
   a controlled restart and preserve their records. Restart only code services
   whose source changed through the established M5 runbook; confirm loaded SHA.
   FreeSWITCH and the database are not dialogue code rebuild targets.
4. Make an end-to-end call through CallActor/FreeSWITCH. Save original audio,
   canonical text, STT, decisions, playback completion/cancellation and timestamps.
   Run story with >2 continuations, side question, topic switch, refusal, symptom,
   “не помню”, slow speech, interrupted ACK and ending the call.
5. Verify questions are genuinely needed; state/evidence survive interruption;
   pause is a listening opportunity, not frozen dead air. Measure end-of-speech
   to first PCM, interruption stop delay and model calls from actual traces.
   Compare recordings blindly for warmth/questionnaire feel. Text replay and
   synthetic PCM do not certify human quality.

## Cost and scale boundaries

No generative inference was added. Selector works on an immutable small legal
set; discourse retains bounded verbatim context rather than an ever-growing
model prompt. Shared preparation avoids a duplicate kernel/mission pass in the
Actor. Normal health actions still use the existing small semantic models and
code-owned safety/consent/evidence.

Millions of registered users do not imply millions of concurrent calls. Capacity
requires measured STT/TTS/model service times, queue limits, replica memory,
tenant admission, storage throughput and overload behavior. This cut adds no
capacity claim. Record model calls per turn/call, p50/p95 timing, RAM and
concurrent throughput before making a production sizing decision.

Optional small local surface generation remains conditional on a real M5
benchmark, bounded grounding validator, cancellation and deterministic fallback.
ADR-025/026/027 no-generative-live constraints were not silently reversed.

Known debt: exact legacy “Не хочу разговаривать.” retains its established
`revoke_consent` mapping, while explicitly ending the current conversation with
“не хочу больше разговаривать” is `stop_call`. A future consent-scope migration
needs explicit compatible outcome handling; do not infer future-call withdrawal
from a newly supported local question refusal. Free personal wording remains
bounded; the engine is not yet an unrestricted generative conversationalist.
