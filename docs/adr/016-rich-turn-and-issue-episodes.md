# ADR-016: Rich turn understanding and generic IssueEpisode memory

Date: 2026-09-09
Status: accepted

## Context

Phase 1 topic mechanics (`active/pending/evidence/resolution`) work, but finite
`TopicFamily` regex as canonical NLU invents issues (e.g. «тошнит» → abdominal pain).
Live call `fs-a80ee60f` proved the failure mode.

## Decision

1. **`SemanticPayload.issue_mentions`** + **`RichUserTurn`** are canonical turn meaning.
2. **`IssueEpisode`** generic memory (`active_episode_id`, `pending_episode_ids`, `issue_episodes`).
3. **`conversation_policy.py`** decides obligations inside DialogueEngine.
4. **`TopicFamily`** demoted to fast hints (sleep only when episodes are canonical).
5. Live LLM path: `SemanticPayload → RichUserTurn → DialogueEngine` — **not** `semantic_from_legacy`.
6. Fast bypass whitelist for short unambiguous turns only; multi-symptom/correction/question → rich path.
7. **Evidence invariant:** no body site or symptom in assistant questions unless user evidence exists.

## Consequences

- «Голова болит и тошнит» → headache episode + associated nausea; no abdominal question.
- fs-592 remains unit regression via topic hints when no IssueEpisode canonical path.
- LLM worker should populate `issue_mentions`; literal extractor enriches when omitted.

## Alternatives Considered

- More `TopicFamily` regex — rejected (finite enum trap).
- Re-import MVP `adaptive_questions.py` — rejected (ADR-015).
