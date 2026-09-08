"""Core edge cases — safety context, interpretation, status, closing."""

from packages.contracts.enums import (
    AnswerJudgement,
    CareState,
    ConsentState,
    DeliveryState,
    FsmState,
    PublicCallStatus,
    RiskLevel,
    SlotStatus,
    TechnicalState,
)
from packages.contracts.mandatory import pilot_mandatory_defaults
from packages.contracts.status import CallStatusSnapshot, SafetySnapshot
from packages.dialogue.interpretation import interpret_user_turn
from packages.dialogue.planner import Planner
from packages.dialogue.state import DialogueState
from packages.safety import SafetyEngine
from packages.safety.rules import match_deterministic_signals
from packages.status import StatusEngine


def _answered(**kwargs) -> CallStatusSnapshot:
    defaults = {
        "call_id": "edge",
        "delivery_state": DeliveryState.ANSWERED,
        "technical_state": TechnicalState.OK,
        "consent_state": ConsentState.ACTIVE,
    }
    defaults.update(kwargs)
    return CallStatusSnapshot(**defaults)


# --- Safety context ---


def test_negated_fall_not_red() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "я не упала")
    assert match_deterministic_signals("я не упала") == []
    assert safety.active_risk == RiskLevel.NONE


def test_third_party_past_fall_not_red() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "вчера соседка упала")
    assert match_deterministic_signals("вчера соседка упала") == []
    assert safety.active_risk == RiskLevel.NONE


def test_self_fall_still_red() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "я упала и не могу встать")
    assert safety.active_risk == RiskLevel.RED


def test_feels_bad_variant_yellow() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "плохо себя чувствую")
    assert "feels_bad" in match_deterministic_signals("плохо себя чувствую")
    assert safety.active_risk == RiskLevel.YELLOW


def test_dismiss_old_episode_keeps_new_red() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "я упала")
    first = safety.active_episode_id
    SafetyEngine.ingest_transcript(safety, "помогите, я действительно упала")
    assert safety.active_risk == RiskLevel.RED
    SafetyEngine.resolve_false_alarm(safety, episode_id=first)
    assert safety.active_risk == RiskLevel.RED


# --- Status: unresolved POSSIBLE blocks GREEN ---


def test_possible_risk_blocks_green() -> None:
    checks = pilot_mandatory_defaults()
    for key in checks:
        checks[key] = True
    safety = SafetySnapshot(active_risk=RiskLevel.POSSIBLE)
    snap = _answered(care_state=CareState.GREEN, mandatory_checks=checks, safety=safety)
    assert StatusEngine.resolve(snap) == PublicCallStatus.YELLOW
    assert StatusEngine.resolve(snap) != PublicCallStatus.GREEN


# --- Interpretation: consent deny ---


def test_consent_deny_not_marked_valid() -> None:
    state = DialogueState(call_id="consent", fsm_state=FsmState.CHECK_CONSENT)
    interp = interpret_user_turn(state, "нет, не согласен")
    assert interp.declines is True
    assert interp.sets_consent == ConsentState.DECLINED

    proposal = Planner.plan_after_user(state, "нет, не согласен", "g1", 1)
    assert state.mandatory_checks["consent"] is False
    assert state.consent_declined is True
    assert state.fsm_state == FsmState.FINAL_CLASSIFICATION
    assert proposal.intent == "consent_declined_final"


def test_defer_consent_not_affirmation() -> None:
    state = DialogueState(call_id="defer", fsm_state=FsmState.CHECK_CONSENT)
    interp = interpret_user_turn(state, "давайте потом")
    assert interp.sets_consent is None
    assert interp.judgement == AnswerJudgement.UNCLEAR
    Planner.plan_after_user(state, "давайте потом", "g1", 1)
    assert state.mandatory_checks["consent"] is False


def test_side_question_does_not_fill_wellness() -> None:
    state = DialogueState(call_id="side", fsm_state=FsmState.DAILY_CHECK)
    Planner.plan_vera_turn(state, 1, "g1")
    assert state.pending_slot == "wellness"
    Planner.plan_after_user(state, "Кто вы такая?", "g1", 2)
    assert state.slots["wellness"] == SlotStatus.OPEN
    assert state.pending_slot == "wellness"


def test_repeat_request_reasks_same_question() -> None:
    state = DialogueState(call_id="repeat", fsm_state=FsmState.DAILY_CHECK)
    Planner.plan_vera_turn(state, 1, "g1")
    proposal = Planner.plan_after_user(state, "Повторите вопрос", "g1", 2)
    assert proposal.intent == "repair_repeat"
    assert "чувствуете" in proposal.speech.lower()
    assert state.slots["wellness"] == SlotStatus.OPEN


def test_backchannel_punctuation_does_not_fill_slot() -> None:
    state = DialogueState(call_id="bc", fsm_state=FsmState.DAILY_CHECK)
    Planner.plan_vera_turn(state, 1, "g1")
    for phrase in ("алло!", "да."):
        Planner.plan_after_user(state, phrase, "g1", 2)
        assert state.slots["wellness"] == SlotStatus.OPEN


def test_goodbye_via_plan_after_user_not_slot_fill() -> None:
    state = DialogueState(call_id="gb", fsm_state=FsmState.DAILY_CHECK)
    Planner.plan_vera_turn(state, 1, "g1")
    proposal = Planner.plan_after_user(state, "до свидания", "g1", 2)
    assert proposal.intent == "goodbye_confirm"
    assert state.slots["wellness"] == SlotStatus.OPEN
    assert state.awaiting_goodbye_confirm is True


def test_goodbye_confirm_yes_finalizes() -> None:
    state = DialogueState(call_id="gby", fsm_state=FsmState.DAILY_CHECK)
    Planner.plan_after_user(state, "до свидания", "g1", 1)
    final = Planner.plan_after_user(state, "да", "g1", 2)
    assert final.intent == "goodbye_final"
    assert state.fsm_state == FsmState.FINAL_CLASSIFICATION


def test_mixed_clause_self_fall_detected() -> None:
    for phrase in (
        "Вчера приходила соседка, а сейчас я упала",
        "Соседка не упала, а я упала",
    ):
        s = SafetySnapshot()
        SafetyEngine.ingest_transcript(s, phrase)
        assert "fall" in match_deterministic_signals(phrase)
        assert s.active_risk == RiskLevel.RED


def test_possible_survives_red_false_alarm() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "всё нормально", semantic_signals=["possible_fall"])
    assert safety.active_risk == RiskLevel.POSSIBLE
    possible_ep = safety.active_episode_id
    SafetyEngine.ingest_transcript(safety, "я упала")
    red_ep = safety.active_episode_id
    SafetyEngine.resolve_false_alarm(safety, episode_id=red_ep)
    assert safety.active_risk == RiskLevel.POSSIBLE
    assert possible_ep not in safety.dismissed_episode_ids


# --- Early goodbye: allow end with incomplete mandatory ---


def test_second_goodbye_ends_call_with_incomplete_mandatory() -> None:
    state = DialogueState(call_id="bye", fsm_state=FsmState.DAILY_CHECK)
    Planner.plan_closing(state, "до свидания", 1, "g1")
    assert state.fsm_state == FsmState.DAILY_CHECK

    final = Planner.plan_closing(state, "до свидания", 2, "g2")
    assert final.intent == "goodbye_final"
    assert state.fsm_state == FsmState.FINAL_CLASSIFICATION
    assert state.call_ended_early is True
    assert state.mandatory_remaining() != []

    checks = dict(state.mandatory_checks)
    snap = _answered(care_state=CareState.UNKNOWN, mandatory_checks=checks)
    assert StatusEngine.resolve(snap) == PublicCallStatus.YELLOW
