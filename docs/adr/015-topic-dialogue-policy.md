# ADR-015: Topic-based conversation policy in DialogueEngine

Date: 2026-09-09
Status: accepted

## Context

Live Zoiper traces showed checklist-first flow (`wellness → mood → sleep → plans`)
misroutes natural speech (e.g. «Плохо спал» at wellness → negative probe). The legacy
`imvera_voice_mvp` had stronger topic tracking (`active_issue`, `pending_issues`,
dimensions) but was regex-heavy and lacked production voice runtime.

ADR-014 freezes telephony path; this ADR extends DialogueEngine policy only.

## Decision

Add `packages/dialogue_engine/topic_tracker.py` inside DialogueEngine:

- `active_topic_family`, `pending_topic_families`, `topic_dimensions_by_family`
- `observe_topic_turn()` — topic switch + dimension extraction
- `next_topic_question()` — ask only uncovered dimensions
- Background slots (`sleep`, `mood`) filled when topic resolves

Wellness/mood/sleep/plans remain **background goals**, not the conversation driver.

Add `never_silent` fallback in reducer: substantive user turns must not yield `[]`.

## Consequences

- «Плохо спал» at wellness activates sleep topic instead of probe_concern
- Multi-topic utterances queue pending families (MVP parity)
- LLM/rich SemanticPayload integration is NEXT (not in this slice)

## Alternatives Considered

- Re-import MVP `adaptive_questions.py` wholesale — rejected (39KB regex, no effects model)
- More `check_path.py` branches — rejected (checklist patching)
