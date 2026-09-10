# ADR-017: Semantic Dialogue ActionPolicy (offline Phase 1)

Status: Proposed / offline experiment only

## Context

DialogueEngine already has a semantic input (`RichUserTurn` / Semantic Kernel), canonical issue memory (`IssueEpisode` / observations), `schedule_next_action`, and `ResponsePlan`. The remaining policy layer is mostly a chain of imperative branches that mixes decision selection with state mutation. This makes it hard to compare alternatives, explain why a question was chosen, or later learn policy weights from call outcomes.

Phase 1 introduces an **offline-only**, pure ActionPolicy experiment inside DialogueEngine. It is not a fourth engine and it is not wired into `schedule_next_action`, reducer, or CallActor.

The hypothesis is falsifiable: a compact state -> candidate actions -> hard constraints -> linear score policy should select acceptable actions at least as reliably as the current scheduler on a frozen corpus, with zero P0 forbidden actions and sub-10ms p99 policy latency on lab hardware.

## Decision

### Pure policy boundary

`ActionPolicy.choose(snapshot, ctx)` MUST be a pure function. It may create local candidates, rejections, feature maps, contributions, and a decision. It MUST NOT mutate `EngineState`, `PolicySnapshot`, episode queues/status, `important_to_share_*`, background coverage, question reservations/attempts, or reducer/effect state.

State changes happen only in a future commit layer after an action is selected. Phase 1 contains no such production commit layer. Current `schedule_next_action` is a mutating baseline, so offline comparison uses an independent deep copy for legacy and an immutable `PolicySnapshot` for ActionPolicy.

### State vector

`PolicySnapshot` contains only generic, post-semantic derived state: active/pending issue episodes, issue status and known semantic dimensions, speaker ownership, pending episode need / suspended obligation, risk level, IMPORTANT_TO_SHARE state, required background-goal coverage, turn number, recent question metadata, per-episode question count, bounded user-burden proxy, and terminal call/FSM state.

Body site and symptom label do not participate in ActionPolicy scoring. They remain surface/evidence data.

### Closed parameterized action catalog

Action kinds stay small and generic:

- `ASK_EPISODE` + `episode_id` + `QuestionNeed`
- `ACK_ONLY`
- `CLARIFY` + target
- `ANSWER_USER`
- `IMPORTANT_TO_SHARE`
- `BACKGROUND_GOAL` + goal
- `REPAIR`
- `CONTROL` + control
- `SAFETY`
- `SUMMARY_CLOSE`
- `GOODBYE_FINAL`
- `LISTEN_META`

There are no body-site actions or per-symptom policy branches. `ASK_EPISODE(onset)` and `ASK_EPISODE(current)` use the same mechanism.

### Hard constraints are non-learnable constitution

Candidates are rejected before scoring when they violate invariants. A negative score is not sufficient. Hard constraints include safety/control/farewell precedence, repair and direct user-question precedence, no speaker interrogation for other-person issues, no ask-already-known / satisfied QuestionNeed, no immediate repeat of the same semantic question, active useful issue blocks background goals and premature close, new grounded issue blocks ITS/summary close, optional background goals are not silently mandatory, ITS meta/unclear stays open, and summary requires resolved ITS.

Future weights may only rank surviving candidates.

### Generic features and linear scorer

Phase 1 does not call `semantic_kernel/information_gain.py` and does not reuse body-site conditionals. Hard constraints answer whether a question may legally be asked; the linear scorer answers whether asking is worth user burden. Named features include information gain, unanswered dimension value, known dimension count, episode question count, resolving episode, user burden, pending-need match, transition preference/penalty, and action/context fit. `fit:episode` is not allowed to dwarf burden/transition features. Score is `sum(weight_i * feature_i)`. Initial weights are human-written and versioned (`POLICY_VERSION`). Every scored candidate logs per-feature contributions.

### Corpus split and anti-overfit rule

The offline corpus has three physically separate splits:

- `development/`: tuning/debug allowed
- `held_out/`: regression corpus; not independent generalization evidence until frozen before weight tuning
- `p0_golden/`: known live regressions; no tuning and 100% pass required
- `challenge_frozen/`: reserved for post-freeze unseen evaluation; must be labeled before first run and never used for tuning

It is invalid to tune weights on a scenario and then count the same scenario as held-out/challenge evidence.

### Two benchmark levels

PolicySnapshot benchmark compares ActionPolicy against the current scheduler on an independent deep copy and normalizes both outputs to canonical `ActionKey` values.

Conversation replay runs `raw turn -> Semantic Kernel/RichUserTurn -> filter_rich_turn_mentions -> atomic_semantic_apply -> PolicySnapshot -> ActionPolicy.choose`. It separates semantic/state-loss failures from policy-selection failures. **Phase 1 gate:** `tests/action_policy/test_pipeline_gate.py` requires `policy_failure == 0` and `nlu_state_loss == 0`; the benchmark CLI exit code enforces the same pair.

ActionPolicy decision inputs MUST NOT import or depend on legacy scheduler signals: `check_path`, `topic_tracker`, `probe_phase`, or `next_open_slot`. `probe_phase` may remain on `PolicySnapshot` for diagnostics/logging only. `unresolved_concern` is derived canonically from Semantic Kernel outputs (negative/uncertain wellness, `vague_issue` ambiguity, `needs_clarification`) when no grounded speaker issue exists.

### Canonical comparison

Examples:

- `episode_*_duration` / `episode_*_onset` -> `ASK_EPISODE:temporal`
- `episode_*_current` -> `ASK_EPISODE:current`
- `probe_concern` -> `CLARIFY:concern`
- `important_to_share` -> `IMPORTANT_TO_SHARE`
- `important_to_share_listen` -> `LISTEN_META`
- `goodbye_final` / `control=stop_call` -> `GOODBYE_FINAL`

Win/loss metrics never compare raw dynamic intent strings.

### Gates

Before any production hook:

- P0 golden: 100% acceptable, 0 forbidden
- held-out: >=95% acceptable after threshold is frozen, 0 forbidden
- P0 repeated-question, premature-close, lost-issue, ITS-meta-close: 0
- ActionPolicy must not regress P0/forbidden metrics versus baseline
- full policy stage p99 target <10ms on lab hardware

Latency covers snapshot/features + candidate generation + constraints + scoring + choose + ResponsePlan bridge. Benchmark uses warm-up plus 100,000 decisions and reports Python version, platform, policy version, p50/p95/p99. The 10ms figure is an acceptance target, never an assumed measurement.

### Logging schema

Each simulator decision records policy version, state summary, generated candidates, hard-rejected candidates with rule/reason, scored survivors, chosen ActionKey, per-feature contributions, expected acceptable/forbidden sets, and placeholders for future outcome labels.

### Explicit non-goals

Phase 1 does NOT import or call ActionPolicy from production scheduler/reducer/CallActor, modify `schedule_next_action`, add a production flag/shadow hook, replace renderer/questions, add phrase banks/microplanner, train weights from calls, call an LLM in the hot path, remove the existing unused Qwen render endpoint, or add body-site policy branches.

## Consequences

If the offline policy fails P0, emits any forbidden action, fails held-out threshold, or misses the latency target, it is not integrated. Features/constraints/weights are revised or the approach is rejected.

If it wins offline, the next ADR amendment may add shadow-only evaluation. Shadow mode is possible because ActionPolicy is pure: the legacy scheduler remains the sole state-mutating production owner while ActionPolicy reads a snapshot and logs a counterfactual decision.

Only after shadow evidence may `schedule_next_action` internals be replaced by `snapshot -> choose -> commit selected action -> ResponsePlan`. Microplanning/surface variation is a later phase under the same hard constraints.
