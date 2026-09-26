# P0b Step 0 — Protocol tri-truth inventory (no behavior change)

Date: 2026-09-26. Source of truth for Step 1 wiring. Every row verified
by grep against HEAD `feature/voice-zoiper-m5`.

## The four sources of "what is required"

| # | Now in code (path:symbol) | Role | Moves to Protocol YAML |
|---|---|---|---|
| 1 | `packages/contracts/mandatory.py:PILOT_MANDATORY_CHECKS` (identity, consent, can_talk, wellness, mood, sleep, plans) | GREEN gate in `StatusEngine._mandatory_complete` (`packages/status/engine.py:63`) | `modes.full.required_slots` (+ `modes.short.required_slots` without bg) |
| 2 | `packages/contracts/mandatory.py:PILOT_SLOT_CHECKS` (wellness, mood, sleep, plans) | `engine.slot_mandatory_remaining` (`engine.py:344`) — blocks close | same table, `modes.*.required_slots` filtered by mode |
| 3 | `packages/dialogue_engine/coverage.py:FILLER_ORDER` (nutrition, medication, mood, sleep) | coverage ladder order (`coverage.py:132,179`, `conversation_policy.py:1440`) | `modes.*.coverage_order` (generated, not copied) |
| 4 | `state.required_background_goals` + `mandatory_background_goals` (+ `21c61be` mode rule in `mission_result.py:146`, `engine.py:347`) | short-vs-full switch: short never requires bg, full does | `modes.short` vs `modes.full` (resolution stays state-driven, lists come from YAML) |
| 5 | `StatusEngine` care/mandatory inputs (`status/engine.py:19-63`) + `_care_state` (`mission_result.py:62`) | YELLOW/RED mapping | `status_impact.*` (adapter later; snapshot already carries `required_checks`) |
| 6 | `complaint_without_negation` + `_mentions_medication` + ITS pivots (reducer/policy) | decline/complaint safety nets — STAY as nets, not the brain | `acts` + `safety_overrides` (declared; enforcement = Step 2) |

## Live counterexamples (one per conflict)

1. **fs-e98331b8 false YELLOW**: wellness/mood/sleep SATISFIED, plans never
   asked → mission PARTIAL → care YELLOW. Sources 1+2+4 disagreed with
   source 3 (coverage closed early). Fixed by mode rule (`21c61be`); the
   YAML makes the rule data, not code.
2. **fs-6e3abff0 false RED via negation**: "ничего не болит" read as
   complaint → urgent_close. Fixed by `complaint_without_negation`
   (`88f172b`, kept as safety net). Protocol records DECLINE semantics;
   Step 2 moves dialogue branching onto Act + NeedQueue.

## Step 1 wiring plan (minimal, one brain)

- New: `packages/dialogue_engine/protocol/pilot_checkin.yaml` +
  `packages/dialogue_engine/protocol/__init__.py` (load once at import).
- `FILLER_ORDER` ← generated from YAML (same tuple, zero behavior delta).
- `PILOT_MANDATORY_CHECKS` ← thin wrapper from YAML full list.
- `mission_result._required_bg_goals` + `engine.slot_mandatory_remaining`
  read the YAML bg set instead of hardcoded `{"mood","sleep","plans"}`.
- `acts:` + `status_impact:` declared in YAML; runtime enforcement of
  acts stays nets until Step 2 (explicitly out of this PR).
- Tests: YAML loads; short excludes bg; full includes all; wrappers equal
  YAML values; class tests fs-e98331b8 (GREEN) + fs-6e3abff0 (no RED).

## Stop condition

Table above complete (it is). Proceed to Step 1 code.
