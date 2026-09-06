---
name: voice-dialogue-quality
description: Design and verify Vera dialogue semantics, slot logic, and spoken surface quality. Use for conversation rules, prompts, and eval scenarios.
---

# Voice Dialogue Quality

## Vera's Job

Conduct a **structured caring check-in** with elderly users on the phone:

- Warm, clear, short sentences
- One question at a time
- Adapt to answers, not rigid script reading
- Never promise actions she cannot perform («я вызову скорую» → only «я записала»)

## Semantic Answer Rules

```text
"ага"     ≠ answer to pending question
"алло"    ≠ answer to pending question
"да"      ≠ answer unless question is yes/no AND context clear
noise     ≠ answer
silence   ≠ answer (NO_ANSWER)
side topic ≠ answer to pending slot
```

**Close slot only on VALID semantic answer** per slot type.

## Slot Lifecycle

```text
OPEN → (VALID answer) → FILLED
OPEN → (decline) → DECLINED
OPEN → (max retries / fatigue) → policy-driven close or escalate
```

Log every transition with `turn_no`, `pending_slot`, `answer_judgement`.

## Spoken Surface

- Renderer produces `canonical_assistant_text`
- TTS receives exact canonical text — no transport rewrite
- Numbers, times: spoken form for Russian elderly audience
- Max sentence length: ~15 words for clarity (soft gate)

## Safety Handoff

Voiseup detects **observations** (raw phrases, confidence).
Core `SafetyEngine` owns RED/YELLOW.
Voiseup may ask **control questions** when policy requires confirmation.

## Eval Scenarios (minimum corpus)

| Scenario | Expected |
|----------|----------|
| Morning check-in | greet → consent reminder if needed → wellness |
| «мне плохо» | observation emitted; not instant hangup |
| «я упал, но не сильно» | negation window respected (Core rules) |
| User tired | shorten, offer callback |
| Goodbye loop | confirm once, then terminal |
| STT garbage | NO_ANSWER, not slot fill |

## Quality Gate

Before claiming dialogue ready:

```text
dialogue unit tests: slot + judgement cases
N-scenario harness: pass rate + failure log
canonical == TTS input: trace proof on 3+ turns
```

## Forbidden

- LLM as sole owner of slot state
- Closing wellness on «угу» with conf > 0.5
- Different text in app vs phone without documented reason
