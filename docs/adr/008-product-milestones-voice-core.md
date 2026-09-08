# ADR-008: Product Milestones — Voice Runtime, Core Boundary, Semantic Contract

**Status:** accepted  
**Date:** 2026-09-06  
**Supersedes / amends:** PROJECT_CONTEXT deployment phases; partial supersede of ADR-002 (Silero as sole TTS); clarifies ADR-003/006 evaluation order; extends ADR-007 interpretation authority.

# ADR-008 scoped sprint (2026-09-06): Zoiper SIP voice loop only.

Active queue: MLX workers → CallActor + LLM semantics → Asterisk/Zoiper.
Deferred (unchanged intent, later milestones): family app, new Core service, notifications, scheduler, `voice.*`/`core.*` schema split.

See product assignment «закрыть голосовой контур через Zoiper».

Repository instructions contained contradictions:

| Topic | Conflict | Resolution |
|-------|----------|------------|
| TTS | Silero in PROJECT_CONTEXT vs CosyVoice/Qwen in ADR-006 | **ADR-003/006 govern provider choice.** Silero examples are historical baseline only. |
| Telephony | FreeSWITCH in skills vs Asterisk in ADR-001 | **FreeSWITCH** (ADR-013). Asterisk/LiveKit lab only. |
| LLM role | Renderer-only in old context vs ADR-007 | **LLM also powers typed interpretation** (SemanticPayload). Planner/State own policy; LLM proposes, server validates. |
| PCM16 20 ms @ 16 kHz | 320 bytes stated | **640 bytes** (320 samples × 2). @ 8 kHz: 160 samples, 320 bytes. |
| Persistence claims | Speech before durable commit | **No save/delivery claims** until `persistence.committed` (or equivalent evidence). |
| Latency SLO | Multiple thresholds | **Single release profile** (§15 of product spec): p50 E2E < 1 s, p95 ≤ 2 s; barge-in p50 < 150 ms. |
| Core | External, unverified | **Minimal real Core** in `services/core` (same monorepo, separate PG schema) until external Core API is confirmed. |

## Decision

### Milestones (execution order)

```text
0  ADR-008 + doctor + doc sync
1  Live mic conversation: real STT + semantic LLM + TTS + PG + async VoiceRuntime
2  Full dialogue/audio integrity (barge-in ledger, corrections, single CALL_ENDED)
3  Core inbox, family API, scheduler, one notification channel
4  Asterisk SIP lab → PSTN trunk
5  Deploy, load, rollback evidence
```

Milestone 1 is **not** replaceable by text-only regression tests.

### Architecture boundaries (unchanged ownership)

```text
Media adapters → audio only
VoiceRuntime   → time, VAD, endpointing, cancel, playback queue (no verdicts)
CallSession    → sequential turn policy (sync core; invoked from runtime thread pool)
Interpreter    → SemanticPayload hypotheses (async provider)
Planner/State  → committed facts, FSM, termination
Renderer       → surface text from typed action + SpeechEvidence
Validator      → allow/deny entire phrase
Persistence    → voice schema + outbox (no help promises)
Core           → families, consent, schedules, public status, app API
```

### Semantic contract

- Single production path: `TurnContext` + `SemanticPayload` → server validation → Planner.
- `UserInterpretation` / rule regex: **protective baseline and text tests only**; voice path requires `InterpretationProvider`.
- Evidence spans must match `raw_text`; consent/control require evidence on current utterance.

### Persistence

- PostgreSQL 16; voice tables under `voice.*` schema (migration path: `migrations/voice/`).
- Core tables under `core.*` (`migrations/core/`).
- `PERSISTED` / save claims only after transaction commit.
- Unique partial index: one `CALL_ENDED` per `call_id`.
- Outbox with lease-based dispatcher to `POST /internal/v1/voice-events`.

### Provider evaluation (not pre-selected winners)

| Layer | First candidate | Benchmark peers |
|-------|-----------------|-----------------|
| VAD | Silero VAD | — |
| STT | Qwen3-ASR-0.6B (ADR-003) | Qwen3-ASR-1.7B, Whisper large-v3-turbo |
| Semantics + Renderer | Qwen3-4B non-thinking | Same hardware profile |
| TTS | Fun-CosyVoice3-0.5B (ADR-006) | Qwen3-TTS size variant |

Winners recorded in `IMVERA_PROVIDER_PROFILE` with checkpoint revision, runtime, precision, hardware. **No silent cloud fallback.**

### Audio

- Internal STT branch: mono PCM S16LE 16 kHz.
- `pcm16_frame_bytes(16000) == 640`; transport may be 8 kHz with stateful resample.
- Full-duplex: STT never receives outbound TTS (ADR-001 + AUDIO_CONTRACT).

### Telephony

- Asterisk ≥ 22.8.0, pinned image digest; chan_websocket binary media + FLUSH_MEDIA.
- Same `CallSession` for browser mic and phone after media-ready.

### CLI contract

`make doctor`, `migrate`, `models-prepare`, `voice-open`, `test-voice`, etc. must run real operations or exit non-zero with `BLOCKED: <reason>`.

## Consequences

- `packages/core/memory_store.py` remains **tests only**; production wiring uses PostgreSQL.
- `services/core` added to monorepo scope.
- Family web client: `apps/family-web` when no external client exists.
- FreeSWITCH is production telephony per ADR-013. Asterisk/LiveKit paths are lab/archive.
- Phase labels in PROJECT_CONTEXT align to milestones 0–5 above.

## References

- Product specification 2026-09-06 (Daniil)
- ADR-001, ADR-003, ADR-006, ADR-007
- Commit audit base: `3750c618`
