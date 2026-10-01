# ADR-026: Grounded warmth through the existing dialogue owners

Date: 2026-10-01
Status: accepted for implementation; live/human warmth acceptance NOT VERIFIED
Branch: `feature/voice-zoiper-m5`

## Context and authorization

Owner requested a more human, warm reception, a competitor comparison and
closer elder-care competitors. Earlier owner constraints persist: no generative
LLM in live conversation; commit/push to m5, not main. ADR-023 and ADR-025 apply.

Warmth is not a random reply bank, a promise of recovery or a fabricated personal
memory. It must follow an accepted conversational event or grounded fact.

## Decision

Keep one reducer/state, one scheduler and one Renderer. Add a bounded optional
`ResponsePlan.acknowledgement_kind`, default None. Its accepted meanings are
`not_recalled`, `resume_mission`, `temporal_answer`, `strong_answer` and
`tolerable_answer`. `acknowledgement_value` carries an accepted duration quote,
default empty. No vendor, second planner, new service, migration or runtime flag.

The reducer marks `TurnContext.answer_not_recalled` only after discharging the
actual pending unknown answer. The scheduler attaches the acknowledgment only
to ordinary question plans, outside risk/RED/control. Renderer formulates it.
An actual custom-goal resumption gets an explicit transition, with no inference
that symptoms recovered. Repeated rendering cannot duplicate that transition.

Replace in place:

| Displaced behavior / owner | Replacement in the same owner |
| --- | --- |
| Unknown answer advances with a bare next question | Reducer event → scheduler → Renderer acknowledgment |
| Custom mission silently resumes its prompt after a complaint | Existing resume_mission_goal_plan declares a transition |
| Renderer picks positive wellness before negative sleep/mood | Accepted negative fact takes precedence in _acknowledge_fills |
| Neutral wellness gets exaggerated positive tails | Bounded neutral acknowledgment; explicit good news still gets a positive response |
| Acknowledgment tail requests another answer before the planned question | Non-question content tails; planner alone owns the question |
| Belly/nausea acknowledgment declares seriousness without evidence | Grounded acknowledgment of discomfort, no clinical severity claim |
| Polite-refusal predicate lacks “разговаривать” | Existing DECLINE matcher recognizes the wording; controls retain existing precedence |
| Rich closing control erases a same-turn grounded complaint | Existing atomic_semantic_apply stores evidence before the unchanged close; mission answers/dispositions are suppressed |
| Positive “неплохо” contains the substring “плохо” | Positive polarity wins; fallback checks word boundaries |
| Accepted duration/severity is followed by a bare next question | Scheduler matches the current quote to accepted episode values; Renderer acknowledges that meaning |
| Multiple active complaints receive only a label plus “учла” | Renderer joins grounded complaint clauses; past/other-person symptoms are excluded from present-tense speaker wording |
| Generic pain question loses its subject after a new symptom | Product copy names the headache; clarification regenerates the same semantic question only when delivered and pending ownership agree |
| Custom mission repair clears the delivered question | Reducer uses the same repair owner as daily calls, preserving question identity and unanswered goals |
| Episode handoff praises pain or loses an unfamiliar body label | Renderer names the next grounded topic and retains unfamiliar labels, without inferring pain from a head site alone |

Conversation-continuity extension (2026-10-01, base `0895277`):
[paired text replay and verification](../live-calls/fs-2baf87ec-conversational.md).
Two existing whole-speech assertions now verify the reaction and exact question
components separately, including their canonical composition. Their clinical,
closing and state assertions remain in place. This is a declared speech change,
not an action-policy change or live/human acceptance claim.

Existing exact call-level consent controls are preserved. This slice does not
redefine “не хочу” or introduce an inference of future consent. Explicit urgent
signals still take the frozen urgent path before ordinary controls or warmth.

## Verification and comparison

New behavioral contracts include memory difficulty without medical reassurance,
partial custom goals, exact pending-goal resumption, mixed positive/negative
facts, neutral tone, one-question ownership, refusal, same-turn evidence,
unchanged emergency/control behavior and idempotent rendering.

Use the same tests against b5adf12 and the new tree, full suite, corpus 500,
hard battery, agent/dream gates, policy differential and Ruff. Exact outputs are
recorded in [current task](../current-task.md).

Freeze 16 common text scenarios and capture attributable transcripts. The
comparison tool rejects changed inputs, suite/language/channel mismatches,
missing evidence metadata and empty “measured” captures. Human warmth is not
scored automatically; untested external providers remain NOT_RUN. Protocol and
official elder-care research: [comparison](../research/elder-care-dialogue-comparison-2026-10-01.md).

## Consequences and limits

These are bounded speech and evidence changes, not proof of arbitrary-language
understanding, neural accuracy, competitor superiority, MOS or live voice quality.
Some engine paths emit earlier existing responses instead of _acknowledge_fills;
their behavior is retained and displayed in the comparison, not silently claimed
as improved. Model artifacts and the live voice environment remain unavailable.

Prosody, perceived warmth, telephony latency and interruption recovery require
actual audio and listeners. Inherited Core admission/status and capacity risks
from ADR-025 remain open. Any cross-call memory must come from grounded, dated
Core evidence with appropriate consent/retention; this slice adds no new memory DB.

## Rollback

Revert the slice commit. New dataclass fields have defaults. No dual live path,
off-switch, credentials, schema migration or paid provider account is introduced.
