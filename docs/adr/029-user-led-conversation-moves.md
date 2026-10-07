# ADR-029: User-led moves inside the existing conversation owner

Date: 2026-10-02
Status: implemented; exact-code CI verified; live audio/human acceptance NOT VERIFIED
Branch: feature/voice-zoiper-m5

## Context

The owner explicitly asks to continue until the questionnaire behavior changes.
Cut1a restored shared selected-question commitment but retained legacy speech.
The [audit](../conversational-move-architecture-2026-10-02.md) identifies three
prerequisites: SDK/Actor producer parity, missing legal conversational moves,
and a real listening lifecycle for acknowledgments without a question.

## Decision

1. Existing TurnUnderstandingV2 is the canonical producer for SDK and Actor.
   Actor keeps post-STT admission first and supplies its precomputed kernel
   result; it must not interpret twice. Models still propose bounded meaning.
2. Evolve the existing ActionPolicy to v10, preserving v9 provenance and medical
   contracts. One candidate builder, constraint filter, scorer and choose loop.
   The existing DecisionRouter delegates only the personal-thread concern to
   that selector; remove the displaced bounded thread branches from legacy.
   Full medical/custom-mission authority does not switch via a hidden flag.
3. Initial invitation, acknowledgment while listening, and real mission return
   are semantic moves. Required nonurgent background information is an
   obligation, not an order to ask immediately. Pending clinical need, fresh
   negative report, safety/control/consent/repair retain deterministic priority.
4. Discourse owns bounded topic/last statement/source/willingness. A two-question
   counter cannot terminate an engaged story. Explicit completion/refusal,
   changed intent, genuine required obligation and silence guide the return.
5. ResponsePlan describes the move; renderer formulates it. Reducer commits
   move/listening state and the existing timer executor waits after actual
   playback. A listening token is not a medical question or a satisfied fact.
   Generation/revision/identity guard stale playback/timers and cancellation.
6. Historical `_product_asked` remains a planning budget, distinct from heard
   delivery. No model mutates EngineState or closes evidence-backed goals.

## Scope and cost

No second engine, reducer, scheduler, FSM or generative renderer. No live LLM
calls are added. Thread context is bounded, not a whole-transcript prompt.
Policy cost is bounded by the small legal candidate set. Registered users and
simultaneous calls are different capacity dimensions: model/provider service
times, queue limits and replicated worker memory require actual benchmarks.
No claim of million-user/100-call throughput follows from SDK tests.

Optional local surface generation remains the conditional ADR-028 B proposal;
it requires actual M5 latency/memory/cancellation/quality and complete grounding
validation before TTS. Existing no-generative-live constraints remain in force.

## Replacement and verification

Displaced owners: direct Actor rich conversion → shared producer; legacy
two-followup thread selector → existing ActionPolicy; question-only thread wait
→ discourse listening token within the same reducer/timer path.

Versioned v10 candidate hashes and tested commit provenance must be truthful;
v9 manifest remains immutable history. The differential tool must compare whole
isolated policy trees, not swap two historical files into eight new modules.
Medical/safety assertions remain strict; explain intended conversational deltas.

Acceptance needs SDK/Actor parity, >2 substantive turns, ACK→USER continuation,
topic shift/return, user question, unknown, refusal, symptoms in a story,
completed/early/cancelled/stale delivery and timeouts. Then actual
CallActor/FreeSWITCH audio/trace and blinded human listening. No bare ready claim.

## Floor-role correction (2026-10-04)

A listening acknowledgment is feedback, not new substantive thread content.
Preserve the story anchor across grammatical confirmations. Explicit completion
or a request for the next conversation move yields the floor; unresolved needs
remain unresolved until actual evidence arrives. The existing selector chooses
one next move after navigation is resolved. Renderer realizes semantic needs
before composing an answer, preserving question binding and retry idempotence.
See [reproduction and limits](../evaluation/conversation-floor-2026-10-04/README.md).

## Source-scoped narrative context (2026-10-04)

The same reducer-invoked discourse writer retains up to6 accepted personal
excerpts of200 characters, with call/utterance identity. The existing grounded
answer owner may quote a matching current-call topic. Clinical/mission recall
keeps its own evidence and ambiguity rules. A narrative quote is not a new
family/medical fact, a satisfied need or cross-call memory. Read-only lookup
adds no generative/model call; absent context remains unknown.

Correction conservatively invalidates the ring; eviction and literal-topic
retrieval limits remain explicit. This repairs topic return, not unrestricted
conversation or global ActionPolicy authority. See the
[product plan](../conversation-product-plan-2026-10-04.md) and
[attributable SDK evidence](../evaluation/personal-context-2026-10-04/README.md).

## Canonical pending and closing correction (2026-10-04)

Use the existing currently_askable_needs as the sole candidate/utility/transition
set, including the reducer-owned active pending need. Current delivered
QuestionNeed wins over intent-name compatibility inference; planned/playing
questions are not heard questions. Same v10 action schema/weights/priority,
truthful candidate publication then actual exact-source CI pin. Historical
v9/v10 provenance remains immutable; global medical authority remains gated
on fresh product need completeness and explained divergences.

Shared morphology/relation ownership retains multiple volunteered facts without
spelling-prefix anatomy guesses or invented pain. The existing closing reducer
interprets a bounded whole no-more acknowledgment only after heard summary;
unknown/new content remains on the ordinary path. Outcome projection honors
the reducer's accepted urgent close before earlier positive facts or stale
external status. Core remains final verdict owner. See the
[source evidence and limits](../evaluation/volunteered-needs-2026-10-04/README.md).

## Open invitation and summary scope (2026-10-07)

The existing reducer consumes a heard open ITS invitation when its existing
discourse writer admitted an attributable personal narrative. This completes
the invitation only: no health/mission goal, absence of complaints, or family
fact is established. The separate required clinical/mission needs remain open.
Pure medication reports and clinical references retain their existing owners;
unclear/unheard invitations are not falsely answered. Release the answered
invitation's delivered-question ownership before the existing ActionPolicy
selects the continuation. No new selector or policy-core version is introduced.

Accepted nonterminal content after SUMMARY re-enters the existing daily-check
state and invalidates the old summary's completion scope. Canonical mission
answers, accepted SDK facts, routine coverage evidence, clinical reports,
personal narrative and user questions retain their original admission owners.
Noise/rejected proposals do not invalidate it. A new summary must be delivered
before its completion opportunity applies; stale/cancelled generations still
cannot establish delivery. Terminal/safety/control/consent owners are unchanged.

This replaces repeated ITS reservations on stories and the reuse of an old
summary to close after new content. Bounded personal memory remains discourse
context. Protocol minima, full medical authority and optional natural surface
remain separate cuts. See [paired source/delivery evidence](../evaluation/continuation-2026-10-07/README.md).
