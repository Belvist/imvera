# ADR-020: Conversational Strategist (constrained dialogue brain)

Date: 2026-09-22
Status: proposed

Amendment 2026-09-30: [ADR-025](025-grounded-dialogue-sdk.md) retires the
generative bridge composer from the live SDK. Its flag/runtime eligibility
and rewriting path are removed; historical proposals below are not active
integration instructions. The owner requires non-generative understanding
and deterministic engine speech.

## Context (verified, not opined)

- Live engine path bypasses the LLM renderer: `packages/voice_runtime/call_actor.py:2374`
  (`_deliver_session_turn` speaks `planner_text` for `from_engine`/engine intents and
  returns; `llm.render_stream` only serves the legacy path). The renderer exists,
  the Qwen worker exists, the live call never sees either.
- Topic selection is a fixed order: `FILLER_ORDER = ("nutrition", "medication", "mood",
  "sleep")` (`packages/dialogue_engine/coverage.py:27`). Live example: «Хорошо себя
  чувствую» → food → meds, regardless of what the person said.
- The LLM worker (`:9103`, `mlx-community/Qwen3-4B-4bit`) is DOWN as of 2026-09-22;
  weights are cached locally, start is possible, render p50/p95 is UNMEASURED.
- Understanding is genuinely good (act classifier model-first, relation XEnc AP 0.939
  in shadow, multi-issue extraction, grounded evidence). The flatness lives BELOW
  understanding: state → fixed policy → Python template → TTS.
- Tests + gates reward invariance (differential 0-unexplained, frozen v9 policy core,
  corpus 500/500). Any behavior change must arrive as blessed-expected, not as drift.
- CI is red on GitHub billing (jobs never start), not on code. Local gates are the
  only truth until the owner fixes billing. `feature/voice-zoiper-m5` is 2 commits
  ahead of `main`.

## Decision

Add a **constrained conversational layer** between `EngineState` and speech, in
independently shippable cuts. Principle (non-negotiable):

> **The model proposes a conversational move; code allows or forbids it; only code
> mutates state. Safety/control/RED/goodbye/summary stay exact deterministic.**

Rejected: fine-tuning a generative Vera now (no corpus of ideal dialogs — ~277 lab
calls, nearly all degenerate; latency unmeasured; hallucinating symptoms to family
is worse than a flat robot; the validator would still have to be built). Rejected:
big-bang rewrite (violates ADR-014 freeze, months without live calls).

## Architecture

```text
STT → TurnUnderstanding → Validator → Reducer → EngineState (authority, unchanged)
    → HardConstraints (safety/stop/consent/asked-set/mission, code)
    → CandidateMoves (code-built, 2–5 legal options)
    → ConversationComposer (Qwen, chooses ONE + renders bridge, Cut 1+; flag-gated)
    → HardValidator (code, supreme; fail → deterministic fallback)
    → TTS (unchanged; canonical == spoken traceable)
```

Single owner per layer holds: Planner (candidates), State (EngineState + discourse
fields), Renderer (composer + templates), Validator (hard validator), Realtime
(delivery/cancel, untouched), Transport (untouched).

### New contracts (all code-owned, LLM never writes them)

**Discourse state** (new EngineState fields, written by reducer from verified
semantics only; Cut 0, no behavior change):
- `current_thread`: `{label, turns_active}` — what the person is talking about now.
- `open_hook`: verbatim span worth following up (e.g. «до двух читал детектив»).
- `asked_signatures`: ring of last 8 question signatures (validator repeat check).
- `last_ack_signature`: what Vera just acknowledged (validator anti-parrot).
- `user_burden`: `{reluctance 0–2, talkative bool}` from turn shape (short/skip/garbage).

**ContextPack** (built per turn, few KB, the only thing the model sees):
- last ≤6 turns (role + text), current user text + verified semantics (acts, issues
  with evidence refs, slots filled this turn), open obligation (pending question id +
  text, active episode), asked-set, suspended obligations, thread/hook/burden,
  candidate moves with ids, hard constraints (e.g. «bridge must not contain a
  question» in Cut 1; fixed question text from Cut 2).

**DialogueMove** (model output, JSON):
```json
{"move_id": "BRIDGE_FOR_FIXED_QUESTION",
 "acknowledge_evidence_ids": ["obs-..."],
 "bridge_text": "Понимаю, неприятно, когда так.",
 "question_id": null}
```
`question_id` stays null until Cut 2, and then must be ∈ allowed list.

**Candidate catalog**: Cut 1: `BRIDGE_FOR_FIXED_QUESTION` only. Cut 2 adds
`FOLLOW_USER_THREAD`, `REFLECT_CONTENT`, `ACK_ONLY`, `ASK_NATURAL_FOLLOWUP`
(from policy-allowed list), `RESUME_MISSION`, `MISSION_QUESTION` (fixed set),
`TRANSITION_TOPIC`. `SAFETY` is never a candidate (deterministic bypass).
`CLOSE` stays deterministic through Cut 2.

### HardValidator rules (Cut 1, extended later, never weakened)

1. `move_id` ∈ candidates offered this turn.
2. Every `acknowledge_evidence_ids` resolves to a real observation/episode in state.
3. Bridge: no `?`, ≤25 words, no promise patterns (вызову/приеду/гарантирую/обещаю…),
   no verdict tokens, no new facts (named entities ∩ state entities only),
   similarity to last Vera line below threshold, Russian.
4. Any violation → deterministic fallback (existing Python bridge), traced with
   `composer.rejected` + reason. Fallback is the release gate, not an embarrassment.

### Latency budget (per turn, measured, not hoped)

STT 0.6 + interpret 0.25 + policy 0.1 + composer (deadline 0.8, fallback instant) +
TTS 0.3 ≈ 1.25 nominal / ~2.0 worst. Composer input is ready at interpret+policy,
so it never blocks the question. If Qwen p95 exceeds the deadline on the lab Mac,
Cut 1 degrades to always-fallback BY MEASUREMENT (still a result: then we cache
bridges or shrink the model — decision by numbers).

### Failure modes (explicit)

- LLM worker down/timeout/invalid JSON/validator reject → deterministic bridge,
  `composer.fallback` traced. Call never waits, never goes silent.
- Worker OOM/model missing at startup → `/health/ready` 503 `llm_cold`, WS rejects
  1013 (same honesty rule as NLP warmup). No calls on a cold brain.
- Composer hallucinates facts → rule 2/3 rejects. Family-visible text is always
  validator-passing or deterministic.

## Staged cuts (each shippable, flaggable, revertible in one line)

- **Cut 0** — worker up + render benchmark report (p50/p95 on live phrases);
  discourse fields + ContextPack builder + catalog (dead paths, unit-tested);
  conversation-quality baseline measured on live traces; corpus v2 scaffolded.
  Gate: numbers recorded, full suite green, zero behavior change (differential clean).
- **Cut 1** — composer writes ONLY the bridge at episode-switch (deterministic bridge
  exists: perfect substitution point), question fixed, validator + fallback, both
  traced. Gate: fallback rate + latency within budget, zero safety violations,
  differential deltas recorded as owner-blessed expected, live bridge acceptance.
- **Cut 2** — strategist picks among the full catalog for background/follow-up turns;
  episode clinical questions stay policy-fixed; `question_id` allowed from list.
  Gate: topic-jump rate down, thread continuity up, mission completion not down.
- **Cut 3** — relation XEnc narrow authority (pending/current goal under validator
  thresholds from calibration); shadow continues. Gate: disagreement rate down.
- **Cut 4** — coverage as utility (information_value/burden/transition_utility from
  ActionPolicy thinking) instead of `FILLER_ORDER` ownership. Gate: owner bless +
  differential; `FILLER_ORDER` stays as tiebreak until then.

## Consequences

- ADR-014 respected: no frozen file touched (manifest covers action-policy core
  only: actions/constraints/features/mandatory/need_value/needs/policy/scorer/
  semantic_signals/snapshot); no new system (same processes, existing `:9103`);
  every cut measurable and revertible; acceptance gates untouched until evidence.
- New quality gates (beside, not instead of, existing): topic-ignored rate,
  unnatural-jump rate, repeat rate, already-known-question rate, ack-relevance,
  thread continuity, groundedness (claims ⊆ evidence), mission completion, safety
  violations (=0), p50/p95 turn latency, composer fallback rate. Baseline in Cut 0.
- Owner actions outside repo: GitHub billing (CI), `main`↔`feature` merge decision.

## Alternatives considered

| Criterion | Big-bang Strategist | Fine-tune speaking model | Staged cuts (chosen) |
|---|---|---|---|
| Latency risk | unknown until built | unknown + training loop | measured at Cut 0/1 |
| Safety | rewrite of guarantees | fluent hallucinations | validator supreme throughout |
| ADR-014 | violates (fourth system) | violates + needs data | compliant |
| Time to audible difference | months | months+ | days (Cut 1) |
| Recovery | rewrite rollback | unlearn impossible | one-line flag |

## Interfaces (sketch, Cut 1)

- `POST :9103/v1/compose` `{context_pack, deadline_ms}` →
  `{move_id, acknowledge_evidence_ids[], bridge_text, question_id}` (existing worker
  extended; same process, no new service).
- Trace stages: `composer.requested / composer.accepted / composer.rejected(reason) /
  composer.fallback`, plus existing `delivery.*`.
- Policy sets `SpeakEffect.bridge_llm_allowed` only for bridge spans; CallActor
  engine branch consults it (the `:2374` bypass gains one constrained door, not a
  demolition).

## NEXT GATE

Cut 0: worker up, benchmark report, baseline metrics, discourse fields + pack builder
merged with zero behavior change. No Cut 1 code before Cut 0 numbers exist.
