# ADR-007: Unified Conversation Loop (Product Edition)

**Status:** Accepted (amended 2026-09-06)  
**Date:** 2026-09-06  
**Owner:** Daniil  

## Context

IMVERA is a **working product**, not a demo shell. Vera conducts natural dialogue, records what the person said with provenance, and delivers structured observations to IMVERA Core/backend so authorized family members see results in the app.

Vera **does not promise** help, emergency response, safety guarantees, or family reaction. Message delivery ≠ help rendered.

This ADR amends the earlier “Investor Voice Demo” framing: the same technical boundaries remain, but acceptance is product-level (dialogue + voice + data + operations).

## Decision

### 1. Single conversation owner

**CallSession** (`packages/dialogue/session.py`) orchestrates each call:

```text
Interpreter (hypothesis) → Safety ingest → RED policy → Planner (commit) → Validator → persistence outbox
```

One state owner. Transport never authors Vera speech. LLM/semantic providers propose; code commits facts, consent, and external actions.

### 2. Typed interpretation before mutation

**TurnInterpretation** is built with `state_version` **before** planner mutates `DialogueState`. Stale or cancelled generations must not apply.

**RuleBasedInterpretationProvider** is the current production-path baseline (`rule_baseline_v1`). **InterpretationProvider** is the plug-in contract for benchmarked LLM interpreters.

### 3. Facts and observations

- **FactRecord** in dialogue state (field, value, quote, turn_id, revision).
- **Multi-fact** utterances extracted clause-wise (`fact_extraction.py`); sleep clauses do not fill mood.
- **CallObservation** + **CallRecordStore** persist observations with idempotency keys before claiming “recorded” or “passed to family” in speech.

### 4. Delivery stages (product)

```text
OBSERVATION_RECEIVED → PERSISTED → CORE_ACCEPTED → APP_AVAILABLE → NOTIFICATION_DELIVERED → VIEWED
```

Speech may only claim stages with evidence (`DeliveryStage` in `packages/contracts/core.py`). Validator blocks help promises and unconfirmed delivery claims.

### 5. Risk handling

On deterministic RED: interrupt survey, persist observation immediately, one clarify question without delaying transfer. `slot_unclear_counts` does not run during `risk_handling`.

### 6. Global controls

`REVOKE_CONSENT`, `STOP_CALL`, `DEFER`, `WRONG_PERSON`, `REPEAT`, `CORRECTION` — unchanged semantics; revoke must eventually update Core consent (integration gate).

### 7. Core boundary

Voiseup emits events and observations. **StatusEngine** / **SafetyEngine** remain domain libraries. Public GREEN/YELLOW/RED in the app requires Core ack — local results are candidates.

## Consequences

- Text and future mic/SIP transports share `CallSession`.
- Backend/app integration uses `CallRecordStore` contract first; replace with Core HTTP/DB without changing dialogue code.
- Tests use public session API; green pytest ≠ voice/backend/load proof.

## Not in scope of this ADR

- STT/TTS production winner (ADR-003, ADR-006)
- PSTN transport (ADR-001)
- Family mobile UI implementation

## Verification status

- Dialogue loop + persistence contract: unit-tested
- Real STT/TTS/audio: **not verified**
- Core HTTP + app visibility: **not verified** — no external IMVERA backend connected in this repo
