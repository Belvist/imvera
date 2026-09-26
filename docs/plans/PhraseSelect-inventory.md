# Step 4 — PhraseSelect inventory (no bank inflation)

Date: 2026-09-27. Speech comes from `questions.py` banks keyed by
ActionId/intent; policy/reducer must not grow new hardcoded lines
(enforced by `tests/test_phrase_discipline.py`).

## Banks (questions.py)

| Bank | Size | Rotation |
|---|---|---|
| `_SLOT_QUESTION_VARIANTS` (wellness/mood/sleep/plans) | 6 each | day + per-call anti-repeat |
| `_PROBE_QUESTION_VARIANTS` (concern/duration/severity/pain_night) | 6 each | day + per-call anti-repeat |
| `_ITS_QUESTION_VARIANTS` | 6 | day + per-call anti-repeat |
| `BACKCHANNEL_ACKS` | 4 | day + per-call anti-repeat |
| `_SLOT_CLARIFICATIONS` | 1 each | fixed (clarify restates, not rotates) |
| `_TOPIC_QUESTIONS` | 1 each | fixed per topic/attr |
| `GREETING_ACK` | 1 | singleton by design |
| summary/goodbye/urgent/partial | via `summary_close_speech` etc. | fixed (single goodbye contract) |

## Pinned singletons (policy/reducer, NOT banks — by design)

`test_phrase_discipline.py` pins exactly 10 literals: mic-check, repair
bare, two clarify prompts, wellness_unknown, meds-today, concern options,
two acks. These are one-off confirmations/repairs, not rotating speech —
moving them into banks adds indirection without value. Any NEW literal
fails the test: put it in a bank.

## Anti-repeat per call (verified, not new)

- Backchannel re-ask excludes `asked_history` + delivered text.
- `_emit_speak` records every marks_question text into `asked_history`.
- Covered by `test_bare_ack_rotates_no_immediate_repeat`,
  `test_backchannel_rephrase.py`, golden single-goodbye test.

## AFFIRM_CLOSE / GOODBYE / SIDE_TOPIC / OTHER

Declared in `pilot_checkin.yaml` with empty effects (option (a) —
untouched). Farewell flows keep existing owners; SIDE_TOPIC stays a
non-plot act (never writes `wellness_concern`).
