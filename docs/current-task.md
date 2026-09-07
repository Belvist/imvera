# Current task — Dialogue Stage 2 (semantic pipeline + outbox)

## Primary assignment

[IMVERA Dialogue Task 2026-09-07](IMVERA_DIALOGUE_TASK_2026-09-07.md) — Stage 2 in progress.  
Architecture: [ADR-009](adr/009-llm-understanding-state-policy.md).

## User outcome (Stage 2 gate)

Смысл → state через единый путь; жалобы зеркалятся без похвалы; outbox §15 не врёт о доставке; PAUSE ack + pause_wait в CallActor.

## Branch / SHA

| Field | Value |
|-------|-------|
| Branch | `feature/voice-zoiper-m5` |
| Last pushed | `e0e86b042067f1860d26f681152c036795c501a4` (Stage 1) |
| Working tree | Stage 2 — **uncommitted** |

## Stage 2 — CHANGED (uncommitted)

**Semantic pipeline:**
- `packages/dialogue/semantic_validator.py` — evidence span, subject, temporal, consent guards
- `packages/dialogue/answer_policy.py` — backchannel ≠ consent; «да» только при доставленном вопросе
- `packages/dialogue/semantic_adapter.py` — validate → policy → bridge
- `packages/dialogue/reducer.py` — единственная мутация state из facts/consent
- `packages/dialogue/planner.py` — `reflect_report`, PAUSE, DialogueReducer
- `packages/contracts/semantic.py` — `control: pause`
- `packages/voice_runtime/call_actor.py` — `adapt_semantic_turn`, outbox finalize, PAUSE wait

**Outbox §15:**
- `packages/contracts/outbox.py` — status machine
- `packages/dialogue/transition_store.py` — metadata `action_outbox`, transitions
- `packages/dialogue/session.py` — snapshot outbox fix
- `packages/voice_runtime/call_actor.py` — `_finalize_outbox_action`, interrupt path
- `tests/test_dispatch_failure_matrix.py`

**Tests:**
- `tests/test_semantic_pipeline.py`
- `tests/test_mixed_nonanswer_sequence.py`
- `tests/test_dispatch_failure_matrix.py`

## Stage 2 — VERIFIED (local, uncommitted)

```bash
make test-dialogue-gates
# 35 passed — policy + CallActor integration

python3 -m pytest tests/ -q
# 170 passed, 4 skipped

# Live LLM (when MLX worker up on :9103):
make test-dialogue-live
# or: IMVERA_LLM_URL=http://127.0.0.1:9103 python3 -m pytest tests/test_llm_live_dialogue.py -v
```

## NOT VERIFIED

- Live Zoiper / real LLM «голова болит» trace
- PG `action_outbox` table wired in `pg_store`
- SIP uplink (parallel uncommitted track)
- Latency baseline doc

## NEXT GATE

1. Commit Stage 2 dialogue (exclude SIP files unless requested).
2. Real-model gate: HttpLLM «голова болит» with trace.
3. Optional: wire `migrations/002_dialogue_transition.sql` to `pg_store`.

## Parallel track (SIP uplink — uncommitted, separate)

`scripts/voice_sip_e2e.py`, `services/asterisk_app/main.py`, `services/voice_gateway/main.py`, `tests/test_voice_stack.py`
