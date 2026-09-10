"""Live-route coverage: outer guards vs conversation_scheduler shadow."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.state import IssueEpisode
from packages.dialogue_engine.turn_understanding import RichUserTurn

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture(autouse=True)
def _shadow_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    yield
    monkeypatch.delenv("IMVERA_ACTION_POLICY_MODE", raising=False)


def _eng() -> DialogueEngine:
    eng = DialogueEngine(call_id="live-shadow", elder_display_name="Тест")
    eng.state, _ = reduce(eng.state, CallStarted())
    eng.state.first_user_turn_received = True
    eng.state.slots["wellness"] = SlotStatus.FILLED
    eng.state.background_goal_status["wellness"] = "answered"
    return eng


def _rich(**kwargs) -> RichUserTurn:
    base = {
        "utterance_id": "live-u-1",
        "raw_text": "ок",
        "dialogue_act": "answer",
        "control": "none",
        "answers_pending_question": False,
        "needs_clarification": False,
    }
    base.update(kwargs)
    return RichUserTurn(**base)


def test_live_scheduler_path_emits_shadow_record() -> None:
    eng = _eng()
    eng.state.issue_episodes["ep-1"] = IssueEpisode(
        episode_id="ep-1",
        primary_label="колено",
        kind="symptom",
        known_attributes={},
        status="open",
    )
    eng.state.active_episode_id = "ep-1"
    effects = eng.on_user_turn(
        "live-u-1",
        "колено болит",
        rich_turn=_rich(utterance_id="live-u-1", raw_text="колено болит"),
    )
    assert effects
    records = eng.drain_action_policy_shadow_records()
    assert records, "scheduler path must evaluate ActionPolicy shadow"
    rec = records[0]
    assert rec["decision_scope"] == "conversation_scheduler"
    assert rec["decision_origin"] == "rich_user_turn"
    assert rec["policy_influenced_output"] is False


def test_live_control_outer_guard_bypasses_scheduler_shadow() -> None:
    eng = _eng()
    eng.on_user_turn(
        "ctl-1",
        "пока",
        rich_turn=_rich(
            utterance_id="ctl-1",
            raw_text="пока",
            control="stop_call",
            dialogue_act="other",
        ),
    )
    records = eng.drain_action_policy_shadow_records()
    assert records == [], (
        "explicit control is OUTER_GUARD — must not count as ActionPolicy evaluated"
    )


def test_live_repair_outer_guard_bypasses_scheduler_shadow() -> None:
    eng = _eng()
    eng.state.waiting_on_slot = "wellness"
    eng.on_user_turn(
        "rep-1",
        "повторите",
        rich_turn=_rich(
            utterance_id="rep-1",
            raw_text="повторите",
            dialogue_act="repair",
        ),
    )
    records = eng.drain_action_policy_shadow_records()
    assert records == [], (
        "repair is OUTER_GUARD — must not count as ActionPolicy evaluated"
    )


# Coverage matrix (documentation for reports):
#
# | Production path                         | Shadow evaluated? | Origin / note        |
# |-----------------------------------------|-------------------|----------------------|
# | schedule_next_action / _schedule_advance| yes               | conversation_scheduler|
# | rich control (stop/defer/revoke/…)      | no                | OUTER_GUARD          |
# | repair / delivery repeat                | no                | OUTER_GUARD          |
# | closing/goodbye FSM                     | no                | OUTER_GUARD          |
# | timer retry direct speak/close          | no                | OUTER_GUARD          |
# | backchannel wait                        | no                | OUTER_GUARD          |
#
# Denominators: total_engine_decisions, outer_guard_decisions,
# scheduler_decisions, shadow_evaluated, shadow_persisted.
# Primary ActionPolicy comparison denominator: shadow_evaluated.
