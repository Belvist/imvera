# CallPhaseMachine — таблица переходов (product spec 2026-09-03)

> Реализация: `policy/fsm.py` (фаза 2).  
> Поток: **GREETING → LISTEN → GOOD|BAD|CRITICAL → RECORD_NOTIFY → CLOSING**

## Состояния

| State | Смысл | Scripted? |
|-------|-------|-----------|
| `GREETING` | Turn 0: pool greeting + wellness Q | **yes** |
| `LISTEN` | Ждём ответ о самочувствии | — |
| `GOOD_PATH` | 2–3 probe questions (GOOD band) | **yes** |
| `BAD_PATH` | Symptom depth questions | **yes** |
| `CRITICAL_PATH` | Fast path — no extra probes | **yes** |
| `RECORD_NOTIFY` | «Записала, родные увидят в приложении» | **yes** |
| `CLOSING` | Goodbye by band + time-of-day | **yes** |
| `CLARIFY` | Silence / low_conf / echo ladder | **yes** |
| `SIDE_ANSWER` | Вопрос абонента, agenda paused | prefer scripted |
| `SAFETY_CONFIRM` | possible_red control Q | **yes** |
| `SAFETY_ACTIVE` | confirmed danger protocol | **yes** |
| `TERMINAL` | Post-hangup no-op | — |

Legacy `WELLNESS_WALK` заменён на `LISTEN` + path states.

## События

| Event | Описание |
|-------|----------|
| `E_CALL_START` | begin_call |
| `E_SPEECH` | Содержательная речь |
| `E_WELLNESS_GOOD` | classify → GOOD |
| `E_WELLNESS_BAD` | classify → BAD or MEDIUM |
| `E_WELLNESS_CRITICAL` | classify → CRITICAL |
| `E_PROBE_DONE` | Good/bad probe step complete |
| `E_PROBES_COMPLETE` | All probes done → notify |
| `E_NOTIFY_DONE` | Record notify spoken |
| `E_CLOSING` / `E_CLOSING_DIRECT` | Прощание |
| `E_EMPTY` | Пустой transcript |
| `E_LOW_CONF` | reason=low_conf |
| `E_ECHO` | reason=echo |
| `E_SAFETY_*` | SafetyBridge |
| `E_SIDE_QUESTION` | Вопрос абонента |
| `E_NARRATIVE` | Длинный рассказ |
| `E_REPAIR` | «Повторите» |
| `E_HANGUP` | Внешнее завершение |
| `E_UNHANDLED` | Catch-all |

## Transition table (core product path)

```text
# --- Opening ---
(OPEN, E_CALL_START, true, play_greeting_pool, GREETING)
(GREETING, E_CALL_START, true, noop, LISTEN)

# --- Listen → branch ---
(LISTEN, E_WELLNESS_GOOD, true, enter_good_path, GOOD_PATH)
(LISTEN, E_WELLNESS_BAD, true, enter_bad_path, BAD_PATH)
(LISTEN, E_WELLNESS_CRITICAL, true, skip_to_notify, CRITICAL_PATH)

# --- Good path (2-3 scripted probes) ---
(GOOD_PATH, E_PROBE_DONE, probes_remain, ask_good_probe, GOOD_PATH)
(GOOD_PATH, E_PROBES_COMPLETE, true, record_notify, RECORD_NOTIFY)

# --- Bad path (symptom depth) ---
(BAD_PATH, E_PROBE_DONE, probes_remain, ask_symptom_probe, BAD_PATH)
(BAD_PATH, E_PROBES_COMPLETE, true, record_notify, RECORD_NOTIFY)

# --- Critical (fast) ---
(CRITICAL_PATH, E_WELLNESS_CRITICAL, true, record_notify, RECORD_NOTIFY)

# --- Notify → close ---
(RECORD_NOTIFY, E_NOTIFY_DONE, true, closing_by_band, CLOSING)
(CRITICAL_PATH, E_NOTIFY_DONE, true, critical_goodbye, CLOSING)

# --- Closing ---
(CLOSING, E_CLOSING_DIRECT, true, terminal, TERMINAL)
(CLOSING, E_HANGUP, true, terminal, TERMINAL)

# --- Global safety ---
(*, E_SAFETY_CONFIRMED, true, safety_enter_active, SAFETY_ACTIVE)
(*, E_REPAIR, true, repair_repeat_last, self)

# --- Clarify ---
(CLARIFY, E_EMPTY, empty_lt_5, silence_ladder, CLARIFY)
(CLARIFY, E_SPEECH, true, resume_listen_or_path, LISTEN|GOOD_PATH|BAD_PATH)

# --- Catch-all ---
(*, E_UNHANDLED, true, warm_ack+log, self)
```

## Closing actions by WellnessBand

| Band | Action | Pool |
|------|--------|------|
| GOOD | `closing_good_time_of_day` | `GOODBYE_GOOD_BY_TIME[утро|день|вечер|ночь]` |
| BAD | `closing_bad` | `GOODBYE_BAD_POOL` |
| MEDIUM | `closing_medium` | `GOODBYE_MEDIUM_POOL` |
| CRITICAL | `closing_critical_fast` | `GOODBYE_CRITICAL_POOL` |

## Totality checklist

- [x] Product path GREETING→CLOSING documented
- [x] `MAX_DISPATCH_DEPTH=4` (`domain/fsm_types.py`, `test_conversation_system_phase2.py`)
- [x] Catch-all `E_UNHANDLED` → warm ack (`policy/fsm.py`)
- [x] Unit tests: `test_every_state_event_has_outcome`, `test_unhandled_never_raises`
- [ ] CONSENT sub-machine (E3 — `core/consent_call.py`, separate from CallPhaseMachine)

## SafetyBridge ↔ FSM (2026-09-03 audit)

- `TurnAnalyzer` **не** вызывает `SafetyEngine.observe()` — один вход на ход через `SafetyBridge.process`.
- `defer_confirmation_for_symptom_detail()` на `SafetyEngine`: ответ «сильно» / глубина симптома не подтверждает RED.
- `confirmed_red` никогда не подавляется wellness-гейтом в `map_to_events`.

## Re-dispatch rules

`resume_listen`, `close_confirm_continue` — max depth 4 → scripted warm ack.
