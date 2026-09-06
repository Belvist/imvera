# Dialogue Specification — Вера

> Phase 1 spec. Implementation: `packages/dialogue/` (Phase 2).

## Principles

1. **FSM owns the scenario** — LLM does not skip mandatory stages.
2. **LLM renders speech only** — no authority on RED/GREEN/public status; semantic hints cap at `POSSIBLE` in SafetyEngine.
3. **Structured interpretation** — `packages/dialogue/interpretation.py` derives affirm/deny/slot-fill from text; Planner does not trust external `VALID` alone.
3. **Slots close only on VALID semantic answers** — see judgement rules.
4. **One pending question** at a time.

## Call FSM states

```text
CALL_START
    → IDENTIFY_PERSON
    → CHECK_CONSENT          # elder only; silence ≠ consent
    → GREETING
    → CHECK_CAN_TALK         # "удобно говорить?"
    → DAILY_CHECK            # slots: wellness, mood, sleep, plans
    → FOLLOW_UP
    → RISK_REVIEW
    → SUMMARY
    → GOODBYE
    → FINAL_CLASSIFICATION
```

### Parallel interrupt (always armed)

```text
RED_SIGNAL
    → CONFIRM_SITUATION
    → INCIDENT_REQUESTED
    → ESCALATION_HANDOFF
    → (terminal sub-flow)
```

FSM may not enter `SUMMARY` or `GOODBYE` while `mandatory_checks` incomplete.

## Mandatory checks (for GREEN)

```text
identity_confirmed
consent_active          # elder only; silence ≠ consent
can_talk_confirmed
wellness_slot           # FILLED or DECLINED
mood_slot
sleep_slot
plans_slot
# pilot mandatory = all seven keys in packages/contracts/mandatory.py
no_active_red_or_yellow
technical_state == OK
delivery_state == ANSWERED
```

Exact list versioned in `schema_version` on call session.

## Slots

| Slot | Question theme | VALID examples | NOT valid |
|------|----------------|----------------|-----------|
| `wellness` | How do you feel | «нормально», «плохо», «голова болит» | «ага», «алло», silence |
| `mood` | Mood | «хорошее», «грустно» | backchannel |
| `sleep` | Sleep | «плохо спал», «нормально» | noise |
| `plans` | Plans for day | «к врачу», «нигде» | side topic only |

Slot status: `OPEN | FILLED | DECLINED`.

## Answer judgement

```text
VALID           → may close pending slot
NO_ANSWER       → silence, unreadable
BACKCHANNEL     → «угу», «ага», «алло» (not answer to open question)
SIDE_TOPIC      → different subject; pending unchanged
UNCLEAR         → ask clarify
DECLINE         → explicit refusal of topic
```

## Turn output (to Validator)

See `packages/contracts/turn.py` — `TurnProposal` from Planner/Renderer.

Validator returns `allowed: bool` and may rewrite `speech` to safe template.

## RED confirm protocol (deterministic)

On `active_risk == RED` or `highest_signal_seen == RED`:

1. Ask control question (template, not LLM-freeform):  
   «Вы сказали, что вам нужна помощь / вы упали. Это так?»
2. On explicit confirm → `signal_resolution = CONFIRMED`, keep `active_risk = RED`.
3. On explicit deny + alternative explanation matching false-alarm rules →  
   `signal_resolution = CONFIRMED_FALSE_ALARM`, may clear `active_risk` per ADR-005.

LLM alone cannot set `CONFIRMED_FALSE_ALARM`.

## Closing

- First «до свидания» → confirm: «Вы хотите закончить разговор?»
- Second short goodbye within window → terminal `GOODBYE` confirmed.
- Continued conversation → reset closing sub-state.

## Voice constraints (Renderer)

- Max ~15 words per sentence (soft Validator gate).
- No promises: «я вызову скорую» → only «я записала».
- Warm, calm, clear — no theatrical emotion.

## Scenario test matrix (Phase 2 gate)

| ID | Input summary | Expected public_status |
|----|---------------|----------------------|
| S01 | Morning check-in all OK | GREEN |
| S02 | «голова кружится» | YELLOW |
| S03 | «упала, не могу встать» + confirm | RED |
| S04 | «не звоните больше» | DECLINED |
| S05 | Ring, no answer | NO_CONTACT |
| S06 | Trunk failed before ring | TECHNICAL |
| S07 | Answered 40s, STT died | TECHNICAL |
| S08 | Answered, STT died, active RED | RED |
| S09 | «не звоните» + «упала» | RED |
| S10 | False alarm «упала»→«убрала таблетки» | per ADR-005 |
| S11 | Vera 10s silent elder | echo gate (runtime) |
| S12 | Real barge-in | playback interrupted |

Tests assert **final StatusEngine output**, not FSM path alone.
