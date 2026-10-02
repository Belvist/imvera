# Cut1b: conversation moves in the existing engine

2026-10-02. Base: `75280deaa0ab2b3e3ff070fba378edd1ef66d542`, target
`feature/voice-zoiper-m5`. Main and loaded M5 services were not changed.
Design recorded before production edits: [ADR-029](../../adr/029-user-led-conversation-moves.md).
Operator/SDK handoff: [integration](../../user-led-conversation-integration.md).

## CHANGED

This cut changes ownership and conversational flow, rather than enlarging the
question bank. The existing ActionPolicy v10 owns grounded nonurgent personal
moves in every router mode: invitation, listening acknowledgment and a return
to an actual unresolved mission need. The two bounded legacy thread branches
were removed. Medical/custom cutover remains separately gated. EngineState and
Reducer remain the single state and writer.

An answer or acknowledgment can yield the floor without posing a question.
The same reducer/playback/timer lifecycle records current planned listening and
the last actually heard origin separately. Cancelled/unheard ACKs, stale timers,
rejected/noisy turns and delayed cached understanding cannot manufacture a
health answer. Terminal goal/slot evidence overrides stale coverage on return.

SDK and Actor share TurnUnderstandingV2. Actor admission precedes final semantic
enrichment, and its accepted precomputed kernel is reused. User questions are
answered before collection; grounded current-call recall requires accepted
speaker evidence. Unsupported answers are explicit unknowns, not invented
preferences, facts or medical advice. An ordinary answer may leave the floor
open; a pending clinical need stays suspended and authoritative.

Actual SDK replay also exposed and corrected perception defects:

- A past social activity or another person's plan is not the caller's plan.
  Single-plan evidence preserves the complete original text; mixed turns use
  the matching literal clause. Explicit absence of plans remains supported.
- A local question refusal plus an affirmative wish/invitation to talk opens
  conversation, without revoking consent or inventing a health value.
- Frequency adverbs cannot become symptom predicates or body sites through
  fuzzy verb/noun matching. Real clinical verbs and unknown body nouns remain.
- A social clause mentioning a daughter cannot suppress a separate present
  speaker complaint. Nominal pain can attach to one grammatical, grounded
  owner; other subjects, ambiguous owners and fictional frames stay separate.
- Yesterday's onset is not proof that the complaint is past-only. The existing
  product planner uses confirmed current evidence with episode, subject, source
  and quote; legacy `active` alone is insufficient. Already volunteered current,
  onset and severity need not be asked again; missing severity still is.

Safety/control/repair/closing and unprobed negative wellness stay above personal
authority. Selector/import/snapshot/bridge failure is logged before exactly one
existing obligations fallback. A telemetry failure does not execute a second
scheduler after a successful selection.

## VERIFIED

Exact commands, aggregate counts and source fingerprints are in
[summary.json](summary.json). [Paired transcripts](before-after.md) show all
15 frozen conversational inputs, including the unchanged medical cases.
[before.json](before.json) was captured in a separate full-source baseline
worktree; [after.json](after.json) is the actual current SDK execution.
The older 16-case daily/custom/control regression suite is captured separately
as `regression-before.json` / `regression-after.json`. Neither suite was edited.

On the 15-case short preset (42 identical user turns), distinct emitted question
identities fell **49 → 26**, and non-question speech presentations rose **8 → 30**.
The fixed-counter return proxy fell **4 → 0**. Ten response sequences changed.
The older 16-case suite changed only the actual purpose-question answer; its
question counts stayed 41. These are SDK behavior counts, not human ratings,
questions per minute or a production completion-rate benchmark. Short fixtures
retain their explicit optional-background preset; mandatory return is checked
separately in `required-background-return-*` and the full corpus gate.

Every capture includes accepted understanding, authoritative state, selected
effects and simulated completed playback. Source fingerprints identify the
uncommitted code envelope; published-commit matching is checked separately.
This is text evidence, not real caller delivery or acoustic latency.

Focused proofs include actual CallSession/Actor admission parity, controlled
single-PCM completion/cancellation, listening identity/generation/timeouts,
cached contextual proposals, local refusal, story continuations, user questions,
clinical compound grounding and actual-goal mission return. Independent
read-only review found no blocker in the reviewed implementation.

Historical v9 core and manifest remain immutable. The active ten-file v10 core
has its own manifest and actual candidate/frozen provenance. Historical and
candidate comparisons import all ten files in isolated subprocesses. No
historical two-file replacement is mixed into a newer eight-file core.

Initial full runs exposed genuine source/plan regressions; they were corrected
without weakening old source or medical assertions. Intended story contracts
changed explicitly: real ACK→USER replaces a two-question forced return.
The report-before-summary test accepts the already existing strong acknowledgment
after current/severity became grounded, retaining strict summary, delivery,
episode and no-fabrication checks.

## NOT VERIFIED

Live M5/FreeSWITCH, original phone audio, listener warmth, human questionnaire
feel, partial-STT/slow-speech endpointing, barge-in, end-of-speech→first-PCM,
model RAM/calls across the whole turn, concurrent capacity and competitor
superiority. Interruption/slow-speech text fixtures are explicitly NOT_RUN for
their required acoustic modalities. Synthetic PCM is not a genuine call.

Local xenc encoder remains an LFS pointer (596070136 bytes expected, SHA256
`560fb3342f1d837ef68383982d963c4a8853594427dbdaf7260f0935abba62c7`).
The two inherited local model-warmup/readiness failures are not waived or
declared green; genuine LFS checkout in GitHub CI is verified separately.

## REMAINING RISKS

Free personal wording is bounded. An ACK is an honest listening move, not an
unrestricted response about every possible subject. No live generative LLM was
added; conditional local surface generation still needs a real M5 benchmark and
grounding/cancellation acceptance. This cut makes no million-user or 100-call
capacity claim. Registered users and concurrent calls require different sizing.

The exact legacy `Не хочу разговаривать.` → `revoke_consent` compatibility debt
remains; explicit current-call ending and local question refusal have distinct
grounded handling. The optional untracked slot classifier differs from the old
historical manifest and is not a pure-policy integrity input; identical loaded
model-bundle readiness is not claimed.

## NEXT GATE

After exact source CI, load the target branch through the established M5 runbook
and record a genuine CallActor/FreeSWITCH call with original audio and trace.
Verify source/model/flags, >2 story continuations, side question, explicit topic
change, refusal, symptoms, unknown, slow speech, interruption and completion.
Measure latency and review recordings blindly. Source publication alone is not
deployment or final voice acceptance.
