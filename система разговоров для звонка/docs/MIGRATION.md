# Migration — cutover от dialogue.py к conversation_system

## Timeline

| Milestone | Flag | Prod spoken | Legacy code |
|-----------|------|-------------|-------------|
| M0 | — | Agent | intact |
| M1 | — | Agent | + new package untested in prod |
| M2 | `shadow` | Agent | new runs parallel, logs diff |
| M3 | `1` | Facade (+ fallback) | legacy fallback on error |
| M4 | `1` | Facade only | delete dialogue/, conversation/ |

## Shadow mode (M2)

```python
plan_old = agent.plan_reply(text, reason)
plan_new = facade.plan_turn(handle, ...)
log_shadow_diff(call_id, turn_no, plan_old, plan_new)
return plan_old  # spoken unchanged
```

Metrics:

- `shadow.event_mismatch` — FSM event differs
- `shadow.reply_similarity` — token overlap < 0.5 → review
- `shadow.semantic_topic_delta` — topics_discussed mismatch

## Rollback

1. Set `MOSS_CONVERSATION_V2=0` in docker/.env  
2. `make up telephony --force-recreate`  
3. No DB migration required (meta JSON backward compatible)

## Dev default (2026-09-03, Phase 4)

Copy `docker/.env.example` → `docker/.env` and set:

```bash
MOSS_CONVERSATION_V2=1
```

Shadow spoken path (default safe):

```bash
MOSS_CONVERSATION_V2=shadow
MOSS_CONVERSATION_V2_SHADOW_SPOKEN=legacy   # or v2 for owner experiments
```

Wiring: `telephony/core/conversation_v2_bridge.py` → `orchestrator.py`
(`new_call`, `process_turn_stream`, `end_call`, `call_greeting`).

## Files to delete at M4

```text
telephony/core/dialogue/          # entire package
telephony/core/conversation/    # entire package
docs/DIALOGUE_4_PLAN.md         # superseded
```

## Files to update at M4

```text
telephony/core/orchestrator.py  # use facade only
telephony/tests/test_dialogue_*.py → test_conversation_system_*.py
voice-lab/dialog_quality.py     # import new runner
AGENTS.md                       # current state
```

## Risk register

| Risk | Mitigation |
|------|------------|
| Live regression | M2 shadow + owner gate M3 |
| Consent break | CONSENT mode isolated sub-machine, port tests first |
| Family Q sync | Reuse end_call PG sync from orchestrator |
| LLM path | ReplyComposer ports flags MOSS_DIALOGUE_LLM_* |
