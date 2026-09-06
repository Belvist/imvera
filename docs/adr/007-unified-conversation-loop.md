# ADR-007: Unified Conversation Loop

**Status:** Accepted  
**Date:** 2026-09-06  
**Context:** Investor Voice Demo v1 requires one skвозной path from user text/audio to Vera speech, with typed interpretation, policy-owned state changes, and no duplicate dialogue brains.

## Decision

1. **CallSession** (`packages/dialogue/session.py`) is the single orchestrator per active call. It sequences: interpret → safety ingest → RED interrupt policy → planner → validator.

2. **TurnInterpretation** (`packages/contracts/interpretation.py`) is the typed hypothesis contract. Interpreter proposes `dialogue_act`, `fact_candidates`, and ambiguity; only planner/policy commits facts into `DialogueState.facts`.

3. **FactRecord** (`packages/dialogue/facts.py`) stores committed slot values with `source_quote`, `turn_id`, and `revision` — not only `SlotStatus.FILLED`.

4. **Global control events** are first-class dialogue acts:
   - `REVOKE_CONSENT` — from any non-terminal state; distinct from `STOP_CALL` (goodbye).
   - `WRONG_PERSON` — ends identification without further polling.
   - `DEFER` at `CHECK_CAN_TALK` — ends call without consent revoke.

5. **Planner** owns action selection including `explain_vera_resume`, `red_confirm_safety`, `terminal_noop`, and repeat limits (`slot_unclear_counts`).

6. **Renderer/Validator** remain downstream of `TurnProposal`; Validator allows empty speech only for `terminal_noop`.

7. **Core boundary:** `StatusEngine` and `SafetyEngine` are libraries invoked by CallSession. Voiseup emits observations; product verdicts await Core ack (unchanged from Architecture Freeze).

## Consequences

- Text runner (`scripts/text_dialogue.py`) and future mic/WebSocket transport share `CallSession.handle_user_text`.
- Semantic LLM provider plugs into interpretation layer behind an interface; rule baseline remains for deterministic gates.
- Tests must use public session API, not manual state mutation after each turn (setup helpers excepted).

## Supersedes / extends

- Extends ADR-004 (FSM) with in-check-in planner flexibility and RED_SIGNAL prompts.
- Does not choose STT/TTS/LLM production winners (see ADR-003, ADR-006).
