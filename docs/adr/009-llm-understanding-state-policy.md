# ADR-009: LLM Understanding + Code State Policy

**Status:** accepted  
**Date:** 2026-09-07  
**Extends:** ADR-004, ADR-007, ADR-008

## Context

Free-form elderly phone speech cannot be handled by regex-only interpretation or unconstrained LLM chat. The product requires auditable memory, attempt limits, and verifiable dialogue outcomes.

## Decision

```text
Interpreter (LLM)  → proposes UserMeaning / SemanticPayload
SemanticValidator  → evidence, subject, time, answer binding
Reducer            → sole state mutation
Planner            → DialogueAction + QuestionLedger
Renderer (LLM)     → surface text from allowed action
SpeechValidator    → policy before TTS
CallActor          → WAIT timers, delivery, cancel generations
Store              → commit_transition before TTS
```

Rejected:

- Regex-only main interpreter
- Second FSM / PlannerV2
- Vector DB as source of truth

## Stage 1 (2026-09-07)

- `QuestionGoal` / `QuestionLedger` with `UNRESOLVED`
- Atomic attempt reserve before TTS; delivery counted separately
- `WAIT` intent handled in CallActor (no TTS during backchannel window)
- Mid-call persistence via `DialogueTransitionStore`

## Consequences

- Acceptance tests target observable behavior (20×«ага», partial CLOSE), not class presence
- Semantic adapter required for contract migration (Stage 2)
