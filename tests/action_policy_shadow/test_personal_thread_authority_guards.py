"""Scoped v10 authority cannot steal safety/closing/control state."""

import pytest

from packages.contracts.enums import FsmState
from packages.dialogue_engine.conversation_policy import TurnContext
from packages.dialogue_engine.decision_router import route_schedule_next_action
from packages.dialogue_engine.response_plan import ResponsePlan
from packages.dialogue_engine.state import CheckPath, EngineState
from packages.dialogue_engine.turn_understanding import RichUserTurn


@pytest.mark.parametrize("field,value", [
    ("safety_mode", "red"), ("risk_handling", True), ("red_state_pending", True),
    ("check_path", CheckPath.URGENT), ("fsm_state", FsmState.SUMMARY),
    ("awaiting_goodbye_confirm", True), ("elder_asked_to_stop", True), ("call_closed", True),
])
def test_personal_authority_excludes_protected_state(monkeypatch, field, value):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    state = EngineState(call_id="guard", fsm_state=FsmState.DAILY_CHECK,
                        current_thread_label="рассказ", thread_last_statement="Внучка приезжала",
                        thread_last_utterance_id="story")
    setattr(state, field, value)
    turn = RichUserTurn(
        utterance_id="story", raw_text="Внучка приезжала", dialogue_act="answer",
        control="none", answers_pending_question=False, needs_clarification=False,
    )
    expected = ResponsePlan(action="none")
    calls = []

    def protected_owner(st, ctx):
        calls.append((st, ctx))
        return expected

    result = route_schedule_next_action(state, TurnContext(turn=turn), legacy=protected_owner)
    assert result is expected and len(calls) == 1
    assert not state.action_policy_router_stats.get("conversation_policy_authoritative")


@pytest.mark.parametrize("stage", ["snapshot", "choose", "bridge"])
def test_personal_selection_failure_is_logged_and_invokes_legacy_once(monkeypatch, stage):
    import packages.dialogue_engine.action_policy.bridge as bridge
    import packages.dialogue_engine.action_policy.policy as policy
    import packages.dialogue_engine.action_policy.snapshot as snapshot

    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    state = EngineState(call_id="failure", fsm_state=FsmState.DAILY_CHECK,
                        current_thread_label="рассказ", thread_last_statement="Внучка приезжала",
                        thread_last_utterance_id="story")
    turn = RichUserTurn(utterance_id="story", raw_text="Внучка приезжала", dialogue_act="answer",
                        control="none", answers_pending_question=False, needs_clarification=False)
    chosen = []

    def fail(*args, **kwargs):
        chosen.append(stage)
        raise RuntimeError("forced selection failure")

    owner, name = {
        "snapshot": (snapshot, "build_policy_snapshot"), "choose": (policy, "choose"),
        "bridge": (bridge, "to_response_plan"),
    }[stage]
    monkeypatch.setattr(owner, name, fail)
    expected = ResponsePlan(action="none")
    calls = []

    def degraded_owner(st, ctx):
        calls.append((st, ctx))
        return expected

    result = route_schedule_next_action(state, TurnContext(turn=turn), legacy=degraded_owner)
    assert result is expected and len(calls) == 1 and chosen == [stage]
    assert not state.slot_values
    assert state.action_policy_router_stats["policy_fallback_legacy"] == 1
    record = state.action_policy_shadow_records[-1]
    assert record["decision_scope"] == "personal_thread"
    assert record["shadow_status"] == "error"
    assert not record["policy_influenced_output"]


def test_telemetry_error_does_not_undo_a_selected_conversation_move(monkeypatch):
    import packages.dialogue_engine.decision_router as router

    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    state = EngineState(call_id="buffer", fsm_state=FsmState.DAILY_CHECK,
                        current_thread_label="рассказ", thread_last_statement="Внучка приезжала",
                        thread_last_utterance_id="story")
    turn = RichUserTurn(utterance_id="story", raw_text="Внучка приезжала", dialogue_act="answer",
                        control="none", answers_pending_question=False, needs_clarification=False)

    def bad_buffer(*args):
        raise RuntimeError("telemetry failure")

    def forbidden_legacy(*args):
        pytest.fail("must not run a second scheduler after successful choose")

    monkeypatch.setattr(router, "buffer_shadow_record", bad_buffer)
    result = route_schedule_next_action(state, TurnContext(turn=turn), legacy=forbidden_legacy)
    assert result.thread_mode == "invite"
    assert state.action_policy_router_stats["conversation_policy_authoritative"] == 1
    assert state.action_policy_router_stats["policy_record_buffer_error"] == 1
