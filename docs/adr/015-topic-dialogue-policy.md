# ADR-015: Issue-first conversation policy in DialogueEngine

Date: 2026-09-09 (updated 2026-09-10)
Status: accepted

## Context

Live Zoiper traces showed checklist-first flow (`wellness → mood → sleep → plans`)
misroutes natural speech (e.g. «Плохо спал» at wellness → negative probe). The legacy
`imvera_voice_mvp` had stronger topic tracking (`active_issue`, `pending_issues`,
dimensions) but was regex-heavy and lacked production voice runtime.

ADR-014 freezes telephony path; this ADR extends DialogueEngine policy only.

## Decision (2026-09-10 — issue-first refactor)

**Single scheduler:** `schedule_next_action(state, turn_context) -> ResponsePlan` in
`conversation_policy.py` is the canonical next-turn entry. The reducer applies events,
mutates state atomically, then calls the scheduler only.

**Policy priority (highest first):**

1. SAFETY 2. CONTROL 3. REPAIR 4. ANSWER USER QUESTION 5. CORRECTION
6. ACTIVE ISSUE 7. PENDING ISSUE 8. IMPORTANT_TO_SHARE 9. BACKGROUND GOAL
10. SUMMARY/CLOSE 11. NEVER SILENT

**Canonical `ResponsePlan`** (`response_plan.py`):

```text
obligation, action, episode_id, question_needs[], acknowledge_facts[],
answer_user_question, safety_class, allowed_facts[], prohibited_inferences[],
close_reason, marks_question
```

Policy does not hardcode question strings; `render_response_plan()` delegates to
`questions.py` (renderer).

**Issue-first memory:** `IssueEpisode` + Observation memory are canonical problem
memory. Generic episodes cover arbitrary symptoms (throat, elbow, ear, neck) without
finite symptom-specific conversation branches.

**Wellness = entry only:** opening asks wellness; semantic kernel ingests; scheduler
decides next. Sleep at wellness creates sleep issue / slot coverage — not
`STANDARD → mood` ladder.

**Background goals = coverage, not ladder:** `wellness/mood/sleep/plans` use
`BackgroundGoalCoverage`: UNSEEN | COVERED_FROM_SPEECH | ASKED | ANSWERED | SKIPPED.
`goal_facts` from free speech close goals. Plans are not mandatory before close.

**IMPORTANT_TO_SHARE:** asked once after issues resolved; yes/no/vague handling;
bridges to summary — not mood ladder.

**Active + pending episodes:** `active_episode_id`, `pending_episode_ids`; finish
active before pending.

**QuestionNeed:** compound semantics via `question_context.py`; information_gain
scoring; satisfaction ≠ memory attribute.

**Demoted authorities:** `next_open_slot()` kept as compatibility helper only;
`topic_tracker` / `probe_phase` / `active_topic` are thin compatibility projections —
not policy drivers.

## Legacy (2026-09-09 slice)

`topic_tracker.py` remains for dimension observation during migration. Background slots
filled when topic resolves or via scheduler `BACKGROUND_GOAL`.

`never_silent` fallback in reducer: substantive user turns must not yield `[]`.

## Consequences

- User meaning drives conversation; background checklist does not auto-advance after episodes
- «Плохо спал» at wellness → sleep issue / slot, not `probe_concern`
- Multi-topic utterances queue pending episodes
- IMPORTANT_TO_SHARE precedes summary when issues were discussed

## Alternatives Considered

- Re-import MVP `adaptive_questions.py` wholesale — rejected (39KB regex, no effects model)
- More `check_path.py` branches — rejected (checklist patching)
- Dual scheduler in reducer — rejected (violates one-owner policy)
