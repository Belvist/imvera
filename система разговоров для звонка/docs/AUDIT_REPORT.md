# Conversation System Audit Report

**Date:** 2026-09-03  
**Scope:** `telephony/conversation_system/` + orchestrator bridge + integration  
**Auditor:** automated agent session (owner request: full E2E audit)

---

## Executive summary

The conversation system is **production-ready** after two critical safety/FSM interaction bugs were fixed. FSM totality is verified (all `CallPhase × FsmEvent` pairs resolve without raise). All automated gates are green.

| Gate | Result |
|------|--------|
| `make test-fast` | **388 OK**, 29 skip |
| `dialog_quality.py --strict` | **18/18 PASS** |
| `synthetic_caller.py --strict` | **30/30 PASS** |
| `live_vera_conversation.py --strict` | **5/5 PASS** (FS loopback + STT) |
| `verify_no_stubs.py conversation_system/` | **32 files OK** |

**Owner gate still open:** one live Zoiper call (RTP + mic) — HTTP/FS harness ≠ SIP media path.

---

## Bugs found and fixed

### 1. CRITICAL — Double `SafetyEngine.observe()` per turn

**Files:** `turn/analyzer.py`, `tests/test_conversation_system_phase1.py`, `tests/test_conversation_system_phase2.py`

**Symptom:** `TurnAnalyzer.analyze()` and `SafetyBridge.process()` both called `observe()` on the shared per-call engine. On «голова болит» the first call set `_awaiting=True`; the second treated the **same utterance** as a control answer and escalated to `confirmed_red` → family alert for routine headache.

**Fix:** Removed `observe()` from `TurnAnalyzer`. Single observation per turn remains in `SafetyBridge.process()`. Added regression tests `test_analyzer_does_not_observe_safety_engine`, `test_headache_not_confirmed_red_on_first_turn`.

### 2. HIGH — Symptom intensifier wedged safety confirm

**Files:** `safety/bridge.py`, `core/safety_engine.py`, `tests/test_conversation_system_phase2.py`

**Symptom:** After «болит голова», safety latched `POSSIBLE_RED` + `_awaiting`. Turn «сильно» (intensity probe answer) produced `uncertain_red` + `E_SAFETY_UNCERTAIN`, blocking `E_PROBES_COMPLETE` → record-notify. Live scenario `bad_symptom_live_turn3` failed.

**Fix:**
- `SafetyEngine.defer_confirmation_for_symptom_detail()` clears awaiting for symptom-depth answers.
- `SafetyBridge._symptom_detail_answer()` + suppress `help_request` mapping for intensifiers with `active_symptom`.
- Test `test_intensifier_defers_safety_and_completes_bad_path`.

---

## FSM / state machine audit

**Implementation:** `policy/fsm.py` + generic `core/fsm.py`

| Criterion | Status |
|-----------|--------|
| Declarative transition table | ✅ `_build_transitions()` |
| Catch-all `E_UNHANDLED` | ✅ `(*, E_UNHANDLED) → warm ack` |
| `MAX_DISPATCH_DEPTH=4` | ✅ caps in `dispatch()` |
| Guards pure (read ctx only) | ✅ guard functions are predicates |
| Global `*` for safety/close/repair | ✅ no state explosion |
| Totality test all phases × events | ✅ `test_every_state_event_has_outcome` |
| Unhandled never raises | ✅ `dispatch` catches → `E_UNHANDLED` |

**Documented gaps (acceptable):**

- `TERMINAL` — only catch-all; no spoken output (by design).
- `CONSENT` — separate path via `core/consent_call.py`, not `CallPhaseMachine`.
- Multi-event dispatch (`_dispatch_events` loops events) — order matters; mitigated by safety defer for symptom path.

**Flag soup:** Extended state lives in `ConversationMemory` + `AgendaManager`; `CallFlags` holds qualitative flags only. `on_good_path` / `record_notified` sync via agenda, not duplicated on `CallFlags` (minor persistence gap if agenda rebuilt from memory alone — low risk).

---

## Security audit (fail-secure)

| Area | Finding | Severity |
|------|---------|----------|
| `confirmed_red` bypass | Never suppressed after wellness gate order in `map_to_events` | ✅ OK |
| Promise guard | `reply/guards.py` strips вызову/позвоню before TTS | ✅ OK |
| LLM safety bypass | Conversation path `scripted_only=True` by default; orchestrator uses `should_use_llm` | ✅ OK |
| Input validation | Orchestrator `_read_body` limits; bridge raises `TurnPipelineError` on facade failure (no fake reply) | ✅ OK |
| Secrets in logs | No tokens/passwords in conversation_system; bridge logs call_id only on warning | ✅ OK |
| Injection in transcript | Text passed to regex classifiers / safety tokens — no SQL/shell | ✅ OK |
| IDOR / API | Product API out of scope; internal `/turn*` gated by orchestrator token/loopback | ✅ OK (integration) |

**Note:** `conversation_v2_bridge.plan_turn_for_call` catches `Exception` and re-raises `TurnPipelineError` — fail-closed (call errors, no silent fallback).

---

## Module review (conversation_system/)

| Module | Notes |
|--------|-------|
| `domain/` | Typed FSM events, `MemoryPatch`, `TurnPlanV2` — consistent |
| `turn/analyzer` | Immutable `TurnUnderstanding`; no safety observe (fixed) |
| `policy/resolver` | Deterministic events; STT uncertain mid-band usable |
| `policy/fsm` | Product paths GOOD/BAD/CRITICAL + clarify ladder |
| `safety/bridge` | Confirm-gate; symptom defer (fixed) |
| `agenda/manager` | Semantic close, intensifier probes, family inject |
| `reply/composer` + `guards` | Pools ≥100; promise/mirror/medical guards |
| `memory/state` | Patches only; RTC via session lock |
| `runtime/session` | `RLock` on plan/commit/end |
| `integration/facade` | Thread-safe session registry |
| `variety/dedupe` | Per-call rotation |

**RTC:** `ConversationFacade` + `ConversationSession.lock` serialize plan/commit/end. `SafetyEngine` per session — no cross-call sharing.

---

## Integration audit

| Integration point | Status |
|-------------------|--------|
| `core/conversation_v2_bridge.py` | Facade-only; no legacy `dialogue.py` |
| `orchestrator.py` | `begin_v2_call`, `plan_turn_for_call`, `commit_turn_for_call`, `end_v2_call` |
| Consent | `plan_consent_turn` when `mirror._consent_call` |
| `voice_runtime` | No direct conversation_system import (HTTP to telephony) — OK |
| Dead imports | No `core.dialogue` in orchestrator |

**Lifecycle:** `begin_call` → `plan_turn` → `commit_turn` → `end_call` verified in facade E2E tests.

---

## Test counts (this audit run)

```
make test-fast              388 OK, 29 skip
dialog_quality --strict     18/18
synthetic_caller --strict   30/30
live_vera_conversation      5/5
verify_no_stubs             32 files clean
```

Conversation-system-specific tests: `test_conversation_system_phase1.py`, `test_conversation_system_phase2.py`, `test_conversation_v2_integration.py`, `test_auto_call_scenarios.py`, `test_scenario_pool_count_and_quality.py`.

---

## Remaining risks (honest)

1. **Live Zoiper not re-verified in this session** after code changes — deploy + one owner call required.
2. **Multi-event FSM dispatch** — if safety and conversational events both fire, order is safety-first; symptom defer added but exotic combos need live monitoring.
3. **`CallFlags` vs agenda fields** — `on_good_path` / `record_notified` not on `CallFlags`; persistence replay from memory-only snapshot incomplete.
4. **STT host dependency** — live harness uses host STT; container STT path differs in prod.
5. **CONSENT machine** — not merged into `CallPhaseMachine`; separate code path.
6. **Barge-in / ESL media** — out of conversation_system scope; step 5 ROADMAP still open.

---

## Deploy

After this audit: `make up telephony` (rebuild telephony image with fixed code).

**Staff Engineer pass (2026-09-03):** See [`VERIFICATION_REPORT.md`](VERIFICATION_REPORT.md) for full matrix. Additional fix: orchestrator reply wav sequential naming on blank STT turns; live_vera expanded to 5 scenarios with retry.

## Files changed in this audit

- `telephony/conversation_system/turn/analyzer.py`
- `telephony/conversation_system/safety/bridge.py`
- `telephony/core/safety_engine.py`
- `telephony/tests/test_conversation_system_phase1.py`
- `telephony/tests/test_conversation_system_phase2.py`
- `система разговоров для звонка/docs/FSM.md`
- `система разговоров для звонка/docs/AUDIT_REPORT.md` (this file)
