# ADR-027: IMVERA Realtime Conversation v1, first delivery slice

Date: 2026-10-01
Status: accepted for runtime fixes; live voice acceptance NOT VERIFIED
Branch: feature/voice-zoiper-m5

## Context

Owner requested a Newo-like natural live conversation, interruption handling,
latency, partial speech, natural Renderer and prosody. Earlier no-generative-live-LLM
constraint remains in force; an optional question about changing it is unanswered.
No model/provider replacement or restored composer is authorized by assumption.
[Newo public architecture](https://newo.ai/platform/newo-zero-hallucination-architecture)
was read on 2026-10-01. It describes language versus truth/action control, field
states and Observer/Supervisor checks. It explicitly denies an absolute guarantee
of error-free generation. It does not specify its STT checkpoint, endpointing,
barge-in latency or prosody settings; vendor statements are not measured IMVERA results.

## Decision

Keep existing FreeSWITCH transport, CallActor, PerceptionSession/TurnManager,
VAD, UtteranceBuilder, single DialogueEngine and canonical speech path. This
slice repairs those owners in place; it adds no competing FSM, service or model.

| Displaced behavior / owner | Replacement in same owner |
| --- | --- |
| UtteranceBuilder waits another 500ms after VAD's silence decision | VAD exposes observed silence; collector counts it toward its total hold, retaining post-roll |
| Speech resumed near post-roll can wait another min_speech window | Existing segment resumes on VAD acoustic candidate; no new STT/semantic turn before final endpoint |
| CallActor awaits LLM cancellation and outbox storage before audio purge/stop | Generation invalidation and PCM purge/stop request precede non-audio work |
| Global barge flag bypasses protected intent policy | Existing TurnManager policy remains authoritative; candidate/confirmation order and user phase preserved |
| bargein_detected emitted after stop | Detection recorded before cancellation, keyed to old generation |
| Intended playback marked as actual playout before TTS | First TTS PCM is marked at provider/cache output, transport start after a successful send |
| Cached/pump path can duplicate first-PCM event | One per-generation first-PCM helper |
| Histogram reads type=timeline while runtime emits stage.timing/stage=timeline | Existing histogram accepts actual and historical schema |
| HttpSTTProvider empty partial stub looks like recognition | Explicit ProviderUnavailable(final-only); no fake partial or silent backend substitution |

VAD.feed's (started, ended) return remains compatible. Optional collector
silence_elapsed_ms receives an observed value; builders without that telemetry
retain existing timing. Acoustic candidate extends an already collecting segment,
not a new semantic turn. Existing VAD thresholds, frame format, engine facts,
controls/consent/safety, question budgets, canonical text and model configuration
are unchanged. Local and downstream callback waits are individually bounded at
250ms; failure is visible. This is NOT proof of the audible barge-in SLO.

Stop traces distinguish local_cancel_ms, stop_request_elapsed_ms and downstream_ack.
They always report audible_stop_verified=false here. +OK from ESL is a command ACK,
not evidence from the telephone speaker. playback.started has the boundary
transport_send_completed and audible_start_verified=false. A blocked send can
escape as one bounded transport race; it cannot restart the cancelled generation.
Existing action finalization still records sent audio as delivery unknown when
cancelled; it never marks an unheard question as delivered.

SDK cancellation follow-up (base 98e1a7c): physical stop also invokes the
existing CallSession.cancel_playout_action using its pending action generation.
This dispatches existing PlayoutCancelled and releases playing/planned question
without creating delivery. Pending actor delivery pointers are cleared for that
generation. Session retains the cancelled effect's address in its existing outbox
index so late completions find terminal CANCELLED before any persistence call.
Partial sent audio stays DELIVERY_UNKNOWN; zero audio stays CANCELLED. Duplicate
cancel does not bump state again. Two real SDK/runtime cases prove resumption
on a new complaint after cancellation and reject delayed completion callbacks.

## Interfaces and readiness

VAD silence_elapsed_ms/speech_candidate → existing collector → final STT.
No partial transcript changes facts, slots or actions. Actual streaming recognition
needs a separately evaluated adapter/checkpoint and revision/final/cancel protocol.
Existing GigaAM production adapter is still final-only. Natural free-form LLM
Renderer is NOT implemented; retired composer remains retired. Prosody knobs and
warm instruction already exist in config/voice-m5.yaml; no unheard tuning is shipped.

[Realtime plan, proof and agent handoff](../realtime-conversation-v1.md) records
same-input PCM comparison, all gate commands and the next live audio gate.

## Consequences

Offline EnergyVad PCM endpoint: 1120→640ms with 500ms VAD silence, 1280→800ms
with 650ms VAD silence, -480ms in each of eight cases. Input hashes match and
post-onset speech order is retained. These are frame-time diagnostic results,
not real model/SIP latency, listener warmth, capacity or competitor superiority.
Barge-in remains operator opt-in through existing flags until live proof; no
new rollout flag or alternate delivery owner. Persistent pipelines can still
incur storage/provider delay after the stop request; p50/p95 require live traces.

## Alternatives considered

- Restore unbounded generative composer: conflicts with current owner constraint
  and reintroduces unverifiable canonical speech. Not selected.
- Switch to a new realtime STT or speech-to-speech vendor now: no elderly Russian
  phone corpus, checkpoint/hardware/SLO comparison or recording available. Not selected.
- Lower every silence threshold: can split slow speech; first remove duplicate
  timer and preserve resumption without modifying the chosen VAD threshold.
- New parallel conversation controller: violates one-owner contract. Not selected.

## Rollback

Revert this slice commit, then use the existing lab barge-in=0 setting on the
stand if its live gate fails. No migration, voice cloning or deployment here.
