# Engineering Architecture — Reference

## FSM Transition Table Format

Use a single declarative list. Example from `telephony/core/fsm.py`:

```
(src_state, event, guard_fn, action_fn, dst_state)
```

- **src_state**: current state name, or `"*"` for any state.
- **event**: input signal (user text class, ESL event, HTTP action).
- **guard_fn(ctx) -> bool**: pure predicate; reads `ctx` only.
- **action_fn(ctx, event) -> Any**: mutates extended state; returns reply/side-effect descriptor.
- **dst_state**: next state after action.

### Invariants

1. Guards never write to `ctx`.
2. Actions never choose the next state (framework applies `dst_state`).
3. First matching guard wins — keep guards mutually exclusive per (src, event).
4. Unhandled (state, event) → `UnhandledEvent` → caller provides safe fallback.

## Extended State vs State Variable

| State variable | Extended state (on Agent/ctx) |
|----------------|-------------------------------|
| Qualitative phase: `CHECKIN`, `SAFETY_ACTIVE` | Counters: `empty_turns` |
| Mutually exclusive modes | Flags: `_help_pending` (temporary, cleared on transition) |
| Drives transition table | Agenda index, facts deque, last_reply |

Rule: if two booleans can be true in invalid combinations → you need more states or a single enum.

## Concurrency Patterns in MossVoice

| Component | Model | Synchronization |
|-----------|-------|-----------------|
| Silero VAD | Multi-thread HTTP | `RLock` in `vad_speech_seconds` |
| Scheduler jobs | Multi-worker PG | `FOR UPDATE SKIP LOCKED` + lease |
| Dialogue FSM | Single-thread per call | RTC — caller must not re-enter |
| STT/LLM HTTP | Async + thread pool | Circuit breaker, bounded timeout |

## Failure Mode Checklist

For each external dependency document:

- **Timeout** (seconds, env override).
- **Retry** (idempotent? max attempts?).
- **Degraded behavior** (fail-open vs fail-closed).
- **Cleanup** on partial failure (WAV files, DB transaction, ESL socket).

## Dialogue-Specific Rules (from AGENTS.md)

New dialogue rules → add regression test first → one row in `DialogueFSM._build_transitions()`.

Never:
- Mirror user phrasing (guard in `reply_looks_broken`).
- Promise autonomous actions (ambulance, call family) — promise-guard replaces before TTS.
- Advance agenda on empty turns or echo-gated input.

## Idempotency Keys

| Operation | Key |
|-----------|-----|
| `enqueue_due_jobs` | elder_id + window |
| `maybe_open` incident | call_id |
| `complete_job` | job_id + lease_owner |
| Family question sync | question_id + pending→asked |
