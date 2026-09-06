# ADR-004: Dialogue FSM Ownership

**Status:** accepted  
**Date:** 2026-09-06

## Context

LLM-only call flows are non-deterministic. IMVERA requires mandatory checks and auditable outcomes.

## Decision

```text
CallStateMachine  → legal states and transitions
Planner           → next intent given FSM + State
State             → sole writer of facts, slots, pending_question
Renderer (LLM)    → proposed speech only
Validator         → allow/deny speech; policy gates
```

LLM:

- **In latency hot path** (Renderer stream)
- **Not in authority path** (no public status, no sole RED decision)

## Prohibited

- Second FSM in transport or TTS layer
- Lua/dialplan generating Vera speech
- Renderer mutating slot status directly

## Consequences

- Phase 2 tests drive FSM + StatusEngine together
- Turn contract in `packages/contracts/turn.py`

## Related

- [DIALOGUE_SPEC.md](../DIALOGUE_SPEC.md)
