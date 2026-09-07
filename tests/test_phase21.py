"""Phase 2.1 regression tests — safety, FSM gates, mandatory pilot scope."""

from packages.contracts.enums import (
    CareState,
    ConsentState,
    DeliveryState,
    FsmState,
    PublicCallStatus,
    RiskLevel,
    SlotStatus,
    TechnicalState,
)
from packages.contracts.mandatory import PILOT_MANDATORY_CHECKS, pilot_mandatory_defaults
from packages.contracts.status import CallStatusSnapshot, SafetySnapshot
from packages.dialogue.fsm import CallFsm
from packages.dialogue.planner import Planner
from packages.dialogue.state import DialogueState
from packages.safety import SafetyEngine
from packages.status import StatusEngine


def _full_mandatory() -> dict[str, bool]:
    return {key: True for key in PILOT_MANDATORY_CHECKS}


def _answered(**kwargs) -> CallStatusSnapshot:
    defaults = {
        "call_id": "p21",
        "delivery_state": DeliveryState.ANSWERED,
        "technical_state": TechnicalState.OK,
        "consent_state": ConsentState.ACTIVE,
    }
    defaults.update(kwargs)
    return CallStatusSnapshot(**defaults)


# --- Safety: LLM has no RED authority ---


def test_llm_semantic_possible_fall_is_not_red() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "всё нормально", semantic_signals=["possible_fall"])
    assert safety.active_risk == RiskLevel.POSSIBLE
    assert safety.active_risk != RiskLevel.RED
    assert safety.highest_signal_seen == RiskLevel.POSSIBLE


def test_llm_semantic_red_label_is_possible_not_red() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "привет", semantic_signals=["red_alert_fall"])
    assert safety.active_risk == RiskLevel.POSSIBLE


def test_llm_semantic_yellow_concern_is_possible_not_yellow() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "всё нормально", semantic_signals=["yellow_concern"])
    assert safety.active_risk == RiskLevel.POSSIBLE
    assert safety.active_risk != RiskLevel.YELLOW
    assert safety.highest_signal_seen == RiskLevel.POSSIBLE


def test_deterministic_fall_still_red() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "я упала")
    assert safety.active_risk == RiskLevel.RED


# --- Safety: false alarm is per-episode ---


def test_false_alarm_then_real_red_restores_active_risk() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "я упала")
    first_episode = safety.active_episode_id
    SafetyEngine.resolve_false_alarm(safety)
    assert safety.active_risk == RiskLevel.NONE
    assert first_episode in safety.dismissed_episode_ids

    SafetyEngine.ingest_transcript(safety, "помогите, я действительно упала")
    assert safety.active_risk == RiskLevel.RED
    assert safety.active_episode_id != first_episode
    assert safety.signal_resolution.value == "UNRESOLVED"


# --- Status: YELLOW beats DECLINED ---


def test_declined_with_yellow_care_is_yellow() -> None:
    s = _answered(consent_state=ConsentState.DECLINED, care_state=CareState.YELLOW)
    assert StatusEngine.resolve(s) == PublicCallStatus.YELLOW


def test_declined_with_yellow_active_risk_is_yellow() -> None:
    safety = SafetySnapshot(active_risk=RiskLevel.YELLOW)
    s = _answered(consent_state=ConsentState.DECLINED, safety=safety)
    assert StatusEngine.resolve(s) == PublicCallStatus.YELLOW


# --- Mandatory: pilot requires all four slots ---


def test_wellness_only_mandatory_is_not_green() -> None:
    checks = pilot_mandatory_defaults()
    checks.update({"identity": True, "consent": True, "can_talk": True, "wellness": True})
    s = _answered(care_state=CareState.GREEN, mandatory_checks=checks)
    assert StatusEngine.resolve(s) == PublicCallStatus.YELLOW


def test_all_pilot_mandatory_can_be_green() -> None:
    s = _answered(care_state=CareState.GREEN, mandatory_checks=_full_mandatory())
    assert StatusEngine.resolve(s) == PublicCallStatus.GREEN


def test_dialogue_state_includes_all_pilot_mandatory_keys() -> None:
    state = DialogueState(call_id="mandatory")
    assert set(state.mandatory_checks.keys()) == set(PILOT_MANDATORY_CHECKS)


# --- FSM: cannot skip identity / consent / can_talk ---


def test_fsm_blocks_advance_without_identity() -> None:
    state = DialogueState(call_id="fsm", fsm_state=FsmState.IDENTIFY_PERSON)
    assert CallFsm.can_advance(state) is False
    CallFsm.advance(state)
    assert state.fsm_state == FsmState.IDENTIFY_PERSON

    state.mandatory_checks["identity"] = True
    CallFsm.advance(state)
    assert state.fsm_state == FsmState.CHECK_CONSENT


def test_fsm_blocks_advance_without_consent() -> None:
    state = DialogueState(call_id="fsm2", fsm_state=FsmState.CHECK_CONSENT)
    state.mandatory_checks["identity"] = True
    assert CallFsm.can_advance(state) is False
    state.mandatory_checks["consent"] = True
    CallFsm.advance(state)
    assert state.fsm_state == FsmState.GREETING


def test_fsm_blocks_summary_until_all_mandatory() -> None:
    state = DialogueState(call_id="fsm3", fsm_state=FsmState.SUMMARY)
    state.mandatory_checks.update({"identity": True, "consent": True, "can_talk": True})
    assert CallFsm.can_advance(state) is False
    for key in PILOT_MANDATORY_CHECKS:
        state.mandatory_checks[key] = True
    assert CallFsm.can_advance(state) is True


def test_planner_opening_wellness_on_call_start() -> None:
    state = DialogueState(
        call_id="planner",
        elder_display_name="Даниил",
        fsm_state=FsmState.CALL_START,
    )
    opening = Planner.plan_vera_turn(state, turn_id=1, generation_id="g1")
    assert opening.intent == "opening_wellness"
    assert "здравствуйте" in opening.speech.lower()
    assert "imvera" in opening.speech.lower()
    assert "даниил" in opening.speech.lower()
    assert "чувствуете" in opening.speech.lower()
    assert state.fsm_state == FsmState.DAILY_CHECK
    assert state.pending_slot == "wellness"
    assert state.mandatory_checks["identity"] is True
    assert state.mandatory_checks["consent"] is True
    assert state.mandatory_checks["can_talk"] is True

    after = Planner.plan_after_user(state, "нормально", "g2", 2)
    assert state.slots["wellness"] == SlotStatus.FILLED
    assert after.intent == "check_mood"


def test_slot_fill_sets_mandatory_for_mood() -> None:
    state = DialogueState(call_id="slot", fsm_state=FsmState.DAILY_CHECK)
    state.pending_slot = "mood"
    Planner.plan_after_user(state, "хорошее", "g1", 1)
    assert state.slots["mood"] == SlotStatus.FILLED
    assert state.mandatory_checks["mood"] is True


def test_planner_arms_pending_slot_when_asking_wellness() -> None:
    state = DialogueState(call_id="pending", fsm_state=FsmState.DAILY_CHECK)
    proposal = Planner.plan_vera_turn(state, turn_id=1, generation_id="g1")
    assert state.pending_slot == "wellness"
    assert state.pending_question is not None
    assert proposal.intent == "check_wellness"
    assert "чувствуете" in proposal.speech.lower()


def test_sequential_slot_questions_fill_all_four_slots() -> None:
    state = DialogueState(call_id="slots", fsm_state=FsmState.DAILY_CHECK)
    turn = 0
    gid = "g-seq"
    answers = {
        "wellness": "нормально",
        "mood": "хорошее",
        "sleep": "нормально спал",
        "plans": "нигде не буду",
    }

    for slot, answer in answers.items():
        turn += 1
        if slot == "wellness":
            question = Planner.plan_vera_turn(state, turn, gid)
        else:
            question = Planner.plan_after_user(state, "", gid, turn)
        assert state.pending_slot == slot
        assert slot in question.intent

        turn += 1
        Planner.plan_after_user(state, answer, gid, turn)
        assert state.slots[slot] == SlotStatus.FILLED
        assert state.mandatory_checks[slot] is True

    assert state.mandatory_remaining() == ["identity", "consent", "can_talk"]


def test_early_goodbye_does_not_corrupt_daily_check_fsm() -> None:
    state = DialogueState(call_id="early", fsm_state=FsmState.DAILY_CHECK)
    proposal = Planner.plan_closing(state, "до свидания", turn_id=1, generation_id="g1")
    assert state.fsm_state == FsmState.DAILY_CHECK
    assert state.closing_requested is True
    assert state.goodbye_count == 1
    assert proposal.intent == "goodbye_confirm"
    assert proposal.fsm_state == FsmState.DAILY_CHECK


def test_sequential_happy_path_call_to_green() -> None:
    """Full pilot call — opening wellness then four slots to GREEN."""
    state = DialogueState(
        call_id="happy",
        elder_display_name="Даниил",
        fsm_state=FsmState.CALL_START,
    )
    gid = "g-happy"
    turn = 0

    def vera_must(intent: str, *, substring: str | None = None) -> None:
        nonlocal turn
        turn += 1
        proposal = Planner.plan_vera_turn(state, turn, gid)
        assert proposal.intent == intent
        if substring:
            assert substring in proposal.speech.lower()

    def user_after_vera(text: str, *, expected_next_intent: str) -> None:
        nonlocal turn
        turn += 1
        proposal = Planner.plan_after_user(state, text, gid, turn)
        assert proposal.intent == expected_next_intent

    vera_must("opening_wellness", substring="чувствуете")
    assert state.fsm_state == FsmState.DAILY_CHECK
    assert state.pending_slot == "wellness"

    slot_flow = (
        ("wellness", "нормально", "check_mood"),
        ("mood", "хорошее", "check_sleep"),
        ("sleep", "спал нормально", "check_plans"),
        ("plans", "дома посижу", "summary"),
    )
    for slot, answer, next_intent in slot_flow:
        user_after_vera(answer, expected_next_intent=next_intent)
        assert state.slots[slot] == SlotStatus.FILLED
        if next_intent.startswith("check_"):
            assert state.pending_slot == next_intent.removeprefix("check_")

    assert state.fsm_state == FsmState.SUMMARY
    assert state.mandatory_remaining() == []

    turn += 1
    first = Planner.plan_closing(state, "до свидания", turn, gid)
    assert first.intent == "goodbye_confirm"
    assert state.fsm_state == FsmState.GOODBYE

    turn += 1
    second = Planner.plan_closing(state, "до свидания", turn, gid)
    assert second.intent == "goodbye_final"
    assert state.fsm_state == FsmState.FINAL_CLASSIFICATION
    assert state.goodbye_confirmed is True

    snap = _answered(care_state=CareState.GREEN, mandatory_checks=dict(state.mandatory_checks))
    assert StatusEngine.resolve(snap) == PublicCallStatus.GREEN
