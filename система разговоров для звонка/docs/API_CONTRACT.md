# API Contract — ConversationFacade ↔ Orchestrator

> Версия: v2 draft (2026-09-03)

## Принципы

1. Orchestrator **не** импортирует `dialogue.Agent` после cutover.
2. Все мутации состояния диалога — внутри `ConversationSession` (per-call lock).
3. TTS boundary guards (`sanitize_segment`) остаются в orchestrator до фазы 4, затем только в `ReplyComposer`.

## Lifecycle

```text
POST /calls
  → facade.begin_call(...) → SessionHandle, greeting?, consent_script?

POST /turn_stream | /turn
  → facade.plan_turn(handle, transcript, reason, stt_confidence) → TurnPlanV2
  → if plan.stream: facade.stream_reply(handle, plan) → segments
  → facade.commit_turn(handle, plan, spoken_text) → TurnCommit

POST /call/end | hangup
  → facade.end_call(handle) → CallSummary
```

## Types

### SessionHandle

```python
@dataclass(frozen=True)
class SessionHandle:
    call_id: str
    internal_id: str  # uuid, not exposed
```

### TurnPlanV2

| Field | Type | Notes |
|-------|------|-------|
| `user_text` | str | Как слышали (может быть пусто) |
| `spoken_reply` | str | Готовый текст если not stream |
| `stream` | bool | LLM streaming path |
| `terminal` | bool | Завершить звонок после TTS |
| `verdict` | str | ok / attention / alert |
| `safety_status` | str | mirror Agent.status |
| `record_notes` | list[str] | Для family verdict |
| `dialogue_step` | int | Legacy events |
| `greeting` | str \| None | First turn override |
| `meta` | dict | scenario_version, phase, goal_kind |

### TurnCommit

| Field | Type |
|-------|------|
| `spoken_text` | str |
| `memory_patches_applied` | int |
| `phase` | str |
| `agenda_cursor` | int |
| `topics_discussed` | list[str] |

### CallSummary

| Field | Type |
|-------|------|
| `verdict` | str |
| `notes` | list[str] |
| `family_questions` | list[dict] |
| `duration_turns` | int |
| `consent_outcome` | str \| None |

## Error handling

| Error | HTTP | Behavior |
|-------|------|----------|
| `SessionNotFound` | 404 | fail closed |
| `TurnPipelineError` | 500 | log; if `MOSS_CONVERSATION_V2=fallback` → legacy Agent |
| `UnhandledFsmEvent` | — | internal; converted to warm_ack in plan |

## Feature flags

| Env | Values |
|-----|--------|
| `MOSS_CONVERSATION_V2` | `0` (default), `shadow`, `1`, `fallback` |

## Compatibility shim (M3)

```python
def turn_plan_to_legacy(plan: TurnPlanV2) -> dict:
    return {
        "text": plan.user_text,
        "intent": None if plan.spoken_reply else "...",
        "fallback": plan.spoken_reply,
        "terminal": plan.terminal,
    }
```

Удалить shim на M4.
