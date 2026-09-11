# ActionPolicy v7 — known live shadow issues

**Status:** known defect — do **not** treat v7 as soft-cutover candidate.  
**Frozen policy SHA:** `61e17934f7be3b10ca5df9b2581cb0a8b853c1fe`  
**Do not fix in Shadow M1.1** — deferred to ActionPolicy v8.

## Defect: pending obligation rejected as `repeat_question`

### Reproduction

```python
from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.state import EngineState, IssueEpisode
from packages.dialogue_engine.action_policy.snapshot import build_policy_snapshot
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.snapshot import TurnContextView

state = EngineState(call_id="repro", turn_seq=3, first_user_turn_received=True)
state.slots["wellness"] = SlotStatus.FILLED
state.background_goal_status["wellness"] = "answered"
state.issue_episodes["ep-1"] = IssueEpisode(
    episode_id="ep-1",
    primary_label="колено",
    kind="symptom",
    known_attributes={"onset": "вчера"},
    status="open",
)
state.active_episode_id = "ep-1"
state.pending_episode_attribute = "current"

snap = build_policy_snapshot(state)
assert snap.last_question_need == "current"  # live builder copies pending
assert snap.outstanding_pending_obligation() is True

decision = choose(snap, TurnContextView())
# Often ASK_EPISODE:severity (or other need) because ASK current is rejected:
# constraints.reject → rule_id == "repeat_question"
```

### Root cause

Live `build_policy_snapshot()` sets:

```text
last_question_need = _last_question_need(intent, pending_episode_attribute)
```

and `_last_question_need` returns `pending` when present. Then `constraints.py`
rejects `ASK_EPISODE:<pending>` as `repeat_question`. Meanwhile `need_value.py`
treats the same pending as a hard obligation. Offline
`PolicySnapshot.from_mapping()` does not always invent this coupling, so the
62/62 challenge missed it.

### Shadow M1.1 expectation

Instrumentation must record:

- `divergence_class = critical_pending_difference` (when shadow ≠ pending ASK)
- `critical_violation = true`
- `critical_violation_flags` contains `critical_pending_discard`
- `cutover_eligible = false`
- `policy_influenced_output = false` (legacy still owns speech)

### Cutover policy

Do **not** run the 100-call / 1000-decision acceptance gate on v7.
Only a short plumbing canary is allowed after M1.1 instrumentation is clean.
v8 must fix pending-vs-repeat priority and add live-builder parity corpus.

## Shadow scope (M1)

ActionPolicy shadow is a **conversation_scheduler** shadow, not a full reducer shadow.

| Path | Shadow? | Notes |
|------|---------|-------|
| `_schedule_advance` → `schedule_next_action` | yes | `decision_scope=conversation_scheduler` |
| Rich control (`stop_call`, defer, revoke, …) | no | outer guard in reducer |
| Repair / delivery repeat | no | outer guard before scheduler |
| Closing / goodbye FSM | no | outer guard |
| Timer retry / `_speak_slot_question` direct | no | outer guard / timer lifecycle |
| Backchannel wait timer | no | outer guard |

Denominators for reports:

```text
total_engine_decisions
outer_guard_decisions
scheduler_decisions
shadow_evaluated
shadow_persisted
```

Primary comparison denominator: `shadow_evaluated`.
