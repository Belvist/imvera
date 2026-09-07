"""Planner clarify path for poor ASR / telephony garbage transcripts."""

from __future__ import annotations

from packages.contracts.enums import AsrQuality, FsmState
from packages.dialogue.planner import Planner
from packages.dialogue.state import DialogueState


def _wellness_pending() -> DialogueState:
    state = DialogueState(
        call_id="asr-clarify",
        family_id="fam-voice",
        elder_display_name="Даниил",
        fsm_state=FsmState.DAILY_CHECK,
    )
    state.greeted = True
    state.pending_slot = "wellness"
    state.pending_question = "Как вы себя чувствуете?"
    state.ensure_goal("wellness")
    return state


def test_low_asr_quality_triggers_clarify_not_close() -> None:
    state = _wellness_pending()
    proposal = Planner.plan_after_user(
        state,
        "",
        "g-low",
        2,
        asr_quality=AsrQuality.LOW,
    )
    assert proposal.intent == "clarify_wellness"
    assert "самочувств" in proposal.speech.lower()


def test_garbage_stt_triggers_clarify() -> None:
    state = _wellness_pending()
    proposal = Planner.plan_after_user(state, "Ответ.", "g-garbage", 2)
    assert proposal.intent == "clarify_wellness"
    assert proposal.intent != "partial_unresolved_close"
