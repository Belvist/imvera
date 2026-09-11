# DialogueEngine universal migration — architecture inventory

Date: 2026-09-11  
Branch context: `feature/action-policy-v8` (inventory only; no CallMission implementation in this doc)  
Status: **PHASE 0 COMPLETE — implementation of mission/goals blocked until this map is accepted**

## Honest diagnosis

Previous work (ActionPolicy v7/v8, shadow, DecisionRouter) optimized the **fixed daily-check scheduler** inside `DialogueEngine`. That improved instrumentation and one pending/delivered bug, but **did not** move the product toward arbitrary app missions.

That direction is superseded for product work. Useful artifacts to keep as foundation/regression:

- `EngineState`, question lifecycle, `IssueEpisode`, `Observation`, `atomic_semantic_apply`
- single-writer reducer / effects / delivery
- ActionPolicy **v8 frozen SHA** as regression benchmark only (`c0fa158…`) — do not mutate
- Shadow/DecisionRouter plumbing can later serve dynamic policy versions; not a cutover path for slot-checklist product

**Forbidden going forward:** new orchestrator, DialogueEngineV2, parallel FSM, second goal store, regex-per-mission-question.

---

## SCOPE

Map production ownership of conversation state and turn meaning so we can generalize **in place** toward:

`CallSession (I/O) → DialogueEngine (ONE state) → understanding → semantic apply → policy → executor → effects`

---

## ENTRY POINTS (production)

| Layer | Module | Role today |
|-------|--------|------------|
| Transport/realtime | `packages/voice_runtime/call_actor.py` | STT → interpret → `CallSession` → TTS/effects |
| Session I/O | `packages/dialogue/session.py` `CallSession` | Persist events, bridge engine↔legacy, drain effects |
| Conversation owner (when flag on) | `packages/dialogue_engine/engine.py` `DialogueEngine` | Event/effect loop, `EngineState` writer |
| Fallback owner (flag off / tests) | `packages/dialogue/planner.py` `Planner` | Legacy scheduler on `DialogueState` |
| Runtime mode | `packages/dialogue_engine/runtime.py` | `dialogue_engine_active()` → `single_writer` else `planner_legacy` |

Activation gate (both required):

```text
IMVERA_DIALOGUE_ENGINE=1 (default)
AND IMVERA_VOICE_DIRECT_WELLNESS_OPENING enabled (via direct_wellness_opening_enabled)
```

When engine active: **`llm_interpret_enabled()` is forced False** — hot-path LLM `/v1/interpret` disabled; CallActor uses SemanticKernel / fast / rich deterministic paths.

---

## OWNERS (as-is vs target)

| Concern | As-is (production, engine on) | As-is (duplicate / leak) | Target |
|---------|-------------------------------|--------------------------|--------|
| Conversation truth | `EngineState` | mirrored via `sync_to_legacy(DialogueState)` | **EngineState only** |
| Turn meaning | CallActor + SemanticKernel + `RichUserTurn` | still builds `UserInterpretation` / slot `FactCandidate` | structured understanding → apply |
| Semantic write | `atomic_semantic_apply` / reducer | legacy Interpreter/Planner on non-engine path | **only** engine apply |
| Next obligation | `conversation_policy.schedule_next_action` (+ ActionPolicy shadow) | Planner when engine off; DecisionRouter soft/policy gated off | one policy over **dynamic** candidates |
| Speech text | ResponsePlan → renderer / SpeakEffect | Validator can still override engine speech in CallActor | renderer only; validator safety gate |
| Transport | CallActor / FreeSWITCH | — | unchanged |
| Persistence | CallSession + store | TransitionStore still Planner-aware | session I/O only |

**Architecture violation (confirmed):** `CallSession` always constructs `DialogueState` + imports `CallFsm`, `Planner`, `Interpreter`, `Validator`, and optionally `DialogueEngine`. Two stacks coexist; engine path syncs into legacy for contracts/persistence.

---

## TURN FLOW (engine on — one user utterance)

```text
CallActor (STT text)
  → Contextual/fast/SemanticKernel (+ rich turn)   [LLM interpret OFF]
  → CallSession.handle_user_text(rich_turn|semantic)
       → DialogueEngine.on_user_turn
            → reducer: understand already done upstream
            → atomic_semantic_apply / issue_memory
            → schedule_next_action (conversation_policy / DecisionRouter)
            → ResponsePlan → SpeakEffect / Timer / EndCall
       → sync_to_legacy(DialogueState)   ← compatibility leak
  → CallActor playout TTS
```

Outer guards (safety/control/repair/timer) remain in reducer — keep deterministic.

---

## COMPONENT CLASSIFICATION

### KEEP (do not rewrite)

| Component | Why |
|-----------|-----|
| `DialogueEngine` + `EngineState` | sole intended conversation owner |
| Question lifecycle PLANNED→PLAYING→DELIVERED | delivery truth |
| `IssueEpisode` + issue_memory | user-raised concerns ≠ mission goals |
| `Observation` (`semantic_kernel/types.py`) | generic fact memory |
| `atomic_semantic_apply` | single reconciliation boundary |
| `SuspendedObligation` | interrupt/resume primitive (needs fields) |
| Effects / outbox / delivery | realtime cancel/barge-in |
| `ResponsePlan` + renderer path | speak contract |
| Frozen ActionPolicy v8 package tree | regression/reference only |
| CallSession as I/O + persistence | correct layer |

### GENERALIZE (in place — product work)

| Component | From | To |
|-----------|------|----|
| `DialogueEngine.__init__` | call_id, name, prior | + `CallMission` / profile input |
| `GoalState` | `slot: str` + SlotStatus | `goal_id`, kind, schema, lifecycle statuses, evidence |
| `EngineState.slots` / PILOT_SLOT_CHECKS | hard universe of 4 | DailyCheckMission **preset** only |
| `Observation` | attribute/value | optional `goal_id` / SATISFIES_GOAL relation |
| Turn understanding | slot-regex + kernel lexicon | schema-validated goal_answers + observations + issues + … |
| `conversation_policy` / ActionPolicy candidates | ASK mood/sleep/severity closed set | ASK_GOAL / FOLLOW_UP / … from state |
| `SuspendedObligation` | slot/episode/attribute | + goal_id, resume_policy |
| Decision apply | choose → legacy schedule can still own output | choose → **one** executor apply (no overwrite) |

### ADAPTER TEMPORARILY

| Component | Role until deleted |
|-----------|-------------------|
| `DialogueState` | persistence / CallActor helpers / sync mirror |
| `packages/contracts/semantic.py` `FactCandidate.field Literal[4]` | wire compat; not meaning owner |
| `UserInterpretation` / `Interpreter` / `Validator` | CallActor bridges & safety checks |
| `Planner` / `CallFsm` / `DialogueReducer` | `planner_legacy` + tests |
| `semantic_from_legacy` / `sync_to_legacy` | dual-stack glue |
| DecisionRouter modes soft/policy | unused until dynamic policy version + real shadow |

### DELETE (only after parity — not now)

| Component | Condition |
|-----------|-----------|
| Production use of Planner as conversation owner | engine path parity on missions + daily-check |
| Slot-only FactCandidate as **source of truth** | Observation+Goal answer path proven |
| Dual `DialogueState` mutation on engine calls | stop sync-as-truth; sync optional export only |
| Hardcoded ActionKind per app question | never add; dynamic labels instead |

**Do not delete:** SemanticKernel, IssueEpisode, Observation, reducer single-writer, delivery.

---

## WHERE BOTH STACKS TOUCH PRODUCTION

Verified by import/use (not speculation):

1. **`CallSession.__init__`** — always `DialogueState`; conditionally `DialogueEngine`
2. **`CallSession.handle_user_text`** — engine `on_user_turn` then `sync_to_legacy`
3. **`CallActor`** — imports Planner, Validator, semantic_adapter **and** dialogue_engine interpreters; branches on `uses_dialogue_engine()`
4. **`DialogueEngine.sync_to_legacy`** — copies engine truth into legacy state for proposals/metadata
5. **`transition_store` / finalize metadata** — still dialogue + engine metadata helpers
6. **Wait expiry** — engine path preferred; planner path **blocked** when engine active (`handle_wait_expired`)

This is the dual ownership to collapse — by retiring legacy **ownership**, not by adding a third brain.

---

## PRODUCT LOCK-IN (why missions fail today)

1. **`FactCandidate.field`** limited to `wellness|mood|sleep|plans` (`packages/contracts/semantic.py`)
2. **`EngineState.slots` / `PILOT_SLOT_CHECKS` / `GoalState.slot`** — checklist universe
3. **`llm_interpret_enabled()` forced off** when engine on — no structured understanding for arbitrary goals
4. **ActionPolicy / conversation_policy** candidate space = episodes needs + background slots, not mission goals
5. **No `CallMission` input** on `DialogueEngine`

Reusable upside: `Observation.attribute` is already a free string; episodes already absorb free-form issues — mission goals must plug into the same apply path.

---

## PRODUCT NORTH STAR (evaluation criterion for every change)

```text
App can assign Vera a task never seen in code.
Human may answer freely, digress, barge-in, correct, ask, report unexpected facts.
Vera: understands meaning, does not lose facts or the mission, handles new topics,
returns to unfinished work, does not re-ask known answers, keeps safety/control,
ends with structured result.
```

Concrete acceptance scenario (still required):

App sends unknown mission goals `utilities_paid`, `groceries_help`. One free utterance answers utilities + raises heating + mentions daughter. Engine satisfies goal with evidence, opens issue/observation, does not re-ask utilities, later continues groceries — **zero mission-specific Python**.

If impossible → architecture not ready.

**Reject any PR that only “improves ActionPolicy” without moving this star.**

---

## WORKING AGREEMENT (architect owns design; agent implements slices)

1. Product outcome is stated in plain language (owner).
2. Architecture, ownership, AI vs deterministic boundaries — architect.
3. Architect attacks the design with failure scenarios before coding.
4. Agent gets a **bounded slice** — no extra engines/stores/orchestrators.
5. Agent “done” is not trusted: diff, SHA, call path, tests, mutation ownership, failure paths reviewed independently.
6. Then behavioural proof (MVP dialogues + missions old MVP cannot do without new Python) → then live SIP.

Reference patterns (external, not vendors to copy blindly): CALM-style interpret≠own-state; schema-constrained structured output + engine grounding; barge-in stays realtime layer.

---

## FIRST MIGRATION SLICE — ARCHITECT-CORRECTED (do not use agent draft)

Agent’s original Slice 1 was **rejected in part**. Corrected constraints:

| ID | Requirement |
|----|-------------|
| A | Ownership map accepted (this file) |
| B | `CallMission` is **input** to existing `DialogueEngine`; daily-check = preset. Wired through **real product path** `CallSession → DialogueEngine` (not engine-only unit toy). |
| C | Separate **immutable `GoalDefinition`** (mission catalog) from runtime **`GoalState`** (attempts/status/answer/evidence). Do **not** overload one type as both. Evolve existing `GoalState` in place; definitions live as mission input / small definition model — **not** `ConversationGoalStateV2` store. |
| D | Structured understanding returns schema-validated candidates only; **does not** write `EngineState`. |
| E | **One canonical apply boundary** (`atomic_semantic_apply` or explicit successor in same place). Same turn: satisfy goal + open IssueEpisode + other observations. |
| F | Daily-check regression stays green. |
| G | No orchestrator / v2 / second state / second scheduler. |
| H | **No silent fallback** custom mission → legacy Planner. Custom mission must fail closed or run on engine path with explicit error — never pretend success via old stack. |
| I | Universal understanding proof must exercise **real understanding entry** (CallActor/session interpret path or the production function it calls). **Forbidden:** hand-built `RichUserTurn` that skips interpretation and only tests apply. |

**Out of slice 1:** new ActionPolicy version / soft cutover / deleting Planner / “80 regex for missions”.

Slice 1 starts only on explicit architect/product go — not automatically after inventory.

---

## NEXT GATE

1. Architect issues bounded Slice 1 implementation brief (this corrected table is the constraint set)  
2. Agent implements **only** that slice  
3. Independent review against north star + H/I anti-cheats  

---

## CHANGED / VERIFIED / NOT VERIFIED

| Label | Content |
|-------|---------|
| **CHANGED** | Inventory + architect corrections to Slice 1 / north star / working agreement |
| **VERIFIED** | Import/ownership recon (prior); Slice 1 corrections are architect authority, not yet coded |
| **NOT VERIFIED** | Slice 1 implementation; live SIP; behavioural parity vs old MVP |
| **REMAINING RISKS** | Agent re-collapsing GoalDefinition into GoalState; proving “understanding” via fabricated RichUserTurn; silent legacy fallback |
| **NEXT GATE** | Explicit go for corrected Slice 1 |
