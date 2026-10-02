# ADR-029: User-led moves inside the existing conversation owner

Date: 2026-10-02
Status: implementation candidate; live audio/human acceptance NOT VERIFIED
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
