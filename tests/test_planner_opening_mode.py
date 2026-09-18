"""Planner direct-wellness opening flag."""

from packages.contracts.enums import FsmState
from packages.dialogue.planner import Planner, direct_wellness_opening_enabled
from packages.dialogue.state import DialogueState


def test_direct_wellness_opening_default_on() -> None:
    state = DialogueState(call_id="t", elder_display_name="Даниил", fsm_state=FsmState.CALL_START)
    proposal = Planner.plan_vera_turn(state, 1, "g1")
    assert proposal.intent == "opening_wellness"
    assert state.fsm_state == FsmState.DAILY_CHECK


def test_full_identity_opening_when_direct_wellness_off(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "0")
    state = DialogueState(call_id="t", elder_display_name="Даниил", fsm_state=FsmState.CALL_START)
    proposal = Planner.plan_vera_turn(state, 1, "g1")
    assert proposal.intent == "identity_intro"
    assert "Вера" in proposal.speech
    assert state.fsm_state == FsmState.IDENTIFY_PERSON
    assert direct_wellness_opening_enabled() is False
