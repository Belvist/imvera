# Current task — Dialogue Stage 1 (QuestionLedger) + SIP uplink

## Primary assignment

[IMVERA Dialogue Task 2026-09-07](IMVERA_DIALOGUE_TASK_2026-09-07.md) — Stage 1 in progress.  
Architecture: [ADR-009](adr/009-llm-understanding-state-policy.md).

## User outcome (Stage 1 gate)

20×«ага» via CallActor + session: ≤2 automatic wellness attempts, 0 invented facts, `UNRESOLVED` + partial CLOSE.

## Branch / SHA

| Field | Value |
|-------|-------|
| Branch | `feature/voice-zoiper-m5` |
| Dialogue work | QuestionLedger, WAIT in CallActor, `DialogueTransitionStore` |

## Stage 1 — CHANGED

**1a (policy loop):**
- `packages/dialogue/question_ledger.py` — QuestionGoal, attempt limits
- `packages/dialogue/planner.py` — BACKCHANNEL→WAIT, UNRESOLVED, reserve/delivery
- `packages/dialogue/state.py`, `packages/contracts/enums.py` — GoalStatus, UNRESOLVED slot
- `packages/dialogue/transition_store.py` — mid-call commit before TTS
- `packages/dialogue/session.py` — `handle_wait_expired`, persistence metadata
- `packages/dialogue/validator.py`, `packages/dialogue/fsm.py` — partial CLOSE
- `migrations/002_dialogue_transition.sql`

**1b (§6.1 WAIT contract):**
- `packages/voice_runtime/wait_state.py` — WaitState, answer_wait + single backchannel_extra
- `packages/voice_runtime/profile.py` — `dialogue_timing_settings()` (7000/2000/30000)
- `config/voice-m5.yaml` — `dialogue_timing` profile
- `packages/voice_runtime/call_actor.py` — event-driven wait, control_epoch, pause on speech
- `tests/test_wait_contract.py`, `tests/test_inference_stop_epoch.py`

## Stage 1 — VERIFIED

```bash
python3 -m pytest tests/ -q
# 157 passed, 2 skipped (2026-09-07)
```

## NOT VERIFIED

- Live Zoiper 20×«ага» with real 7s timers
- PG migration 002 applied / outbox §15 wired
- PAUSE wait (`pause_wait_ms`) end-to-end
- `test_dispatch_failure_matrix.py` (§15 four points)
- Latency baseline doc (Phase 0)

## NEXT GATE

Stage 1b remainder: outbox status machine + dispatch failure matrix. Then Stage 2 (`SemanticAdapter`).

## Parallel track (SIP uplink)

See uncommitted `call_actor.py` / `voice_sip_e2e.py` — capture topology still open.
