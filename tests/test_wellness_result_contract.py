from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from packages.contracts.core import CallResultSnapshot, DeliveryStage, TerminationReason
from packages.contracts.enums import RiskLevel, SlotStatus
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn
from packages.dialogue_engine.state import GoalLifecycle

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> CallSession:
    from packages.dialogue_engine import caller_memory

    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")
    monkeypatch.delenv("IMVERA_TINYLLM_MODEL", raising=False)
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    monkeypatch.delenv("IMVERA_PG_URL", raising=False)
    monkeypatch.setattr(caller_memory, "_store_dir", lambda: tmp_path / "phrase_memory")
    result = CallSession(
        call_id="wellness-result-contract",
        family_id="synthetic-family",
        elder_display_name="Тест",
        store=InMemoryCallRecordStore(),
    )
    _deliver(result, result.start())
    return result


def _deliver(session: CallSession, result: SessionTurnResult) -> None:
    assert result.persist_ok, result.persist_error
    assert result.validated.allowed
    assert session._engine is not None
    effects = ([result.speak_effect] if result.speak_effect else []) + list(
        result.followup_speak_effects
    )
    for effect in effects:
        session._engine.on_playout_started(effect.generation, effect.question_id)
        assert session.mark_spoken_action(effect.generation_id)


def _reply(session: CallSession, text: str) -> SessionTurnResult:
    engine = session._engine
    assert engine is not None
    uid = f"u-{session.turn_id + 1}"
    slot = engine.answer_context_slot()
    parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
    turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
    result = session.handle_user_text(text, utterance_id=uid, rich_turn=turn)
    _deliver(session, result)
    return result


def _exhaust(session: CallSession, text: str) -> None:
    engine = session._engine
    assert engine is not None
    for attempt in range(3):
        result = _reply(session, text)
        assert not session.state.consent_declined
        assert not session.state.call_revoked
        if attempt < 2:
            assert result.proposal.intent == "clarify_wellness"
            assert engine.state.slots["wellness"] == SlotStatus.OPEN
            assert engine.answer_context_slot() == "wellness"
    assert result.proposal.intent == "wellness_unknown"
    assert not engine.state.call_closed
    assert engine.state.slots["wellness"] == SlotStatus.UNRESOLVED
    assert engine.state.goals["wellness"].lifecycle == GoalLifecycle.UNCLEAR
    assert engine.state.observations["wellness_unknown"] == text
    assert "wellness" not in engine.state.slot_records
    assert session.state.slots["wellness"] == SlotStatus.UNRESOLVED
    assert not session.state.mandatory_checks["wellness"]


def _public_result(session: CallSession, monkeypatch: pytest.MonkeyPatch) -> dict:
    from services.api import voice
    from services.voice_service import main as voice_service

    assert session.finalize_if_needed() == (True, None)
    snapshot = session.get_persisted_result()
    assert snapshot is not None
    restored = CallResultSnapshot.model_validate_json(snapshot.model_dump_json())
    assert restored == snapshot
    monkeypatch.setattr(voice, "_store", session.store)
    monkeypatch.setattr(voice_service, "_store", session.store)
    body = voice.get_call(session.state.call_id, session.state.family_id)
    assert voice_service.call_result(session.state.call_id, session.state.family_id) == body
    assert body == restored.model_dump(mode="json")
    for handler in (voice.get_call, voice_service.call_result):
        with pytest.raises(HTTPException) as error:
            handler(session.state.call_id, "different-family")
        assert error.value.status_code == 404
    assert body["delivery_stage"] == DeliveryStage.PERSISTED.value
    assert body["public_status"] is None
    return body


@pytest.mark.parametrize("text", ["Не знаю.", "Абракадабра."])
def test_exhausted_wellness_survives_public_result(
    session: CallSession, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    _exhaust(session, text)
    body = _public_result(session, monkeypatch)
    assert body["call_ended"] is True
    assert body["partial"] is True
    assert body["termination_reason"] == TerminationReason.DISCONNECTED.value
    assert body["outcomes"] == {
        "call_outcome": "TECHNICAL",
        "mission_status": "PARTIAL",
        "family_status": "UNSET",
    }
    mission = body["mission_result"]
    assert mission == body["metadata"]["mission_result"]
    assert body["outcomes"] == body["metadata"]["outcomes"]
    wellness = next(goal for goal in mission["goals"] if goal["goal_id"] == "wellness")
    assert wellness["lifecycle"] == "UNCLEAR"
    assert wellness["value"] is None
    assert wellness["evidence"] == []
    assert "wellness" not in body["facts"]
    legacy = body["metadata"]["dialogue_state"]
    assert legacy["slots"]["wellness"] == "UNRESOLVED"
    assert legacy["consent_declined"] is False
    assert legacy["call_revoked"] is False
    assert session.safety.active_risk == RiskLevel.NONE
    assert not any(
        "CONSENT" in event.event_type or event.event_type == "RED_SIGNAL"
        for event in session.store.get_events(session.state.call_id, session.state.family_id)
    )
    assert f"wellness_unknown:{text}" in mission["observations"]


def test_completed_call_with_unknown_wellness_is_still_partial(
    session: CallSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _exhaust(session, "Не знаю.")
    assert _reply(session, "Не знаю.").proposal.intent == "important_to_share"
    assert _reply(session, "Дома буду.").proposal.intent == "summary"
    assert _reply(session, "Нет, ничего.").proposal.intent == "goodbye_final"
    body = _public_result(session, monkeypatch)
    assert body["outcomes"] == {
        "call_outcome": "COMPLETED",
        "mission_status": "PARTIAL",
        "family_status": "UNSET",
    }
    assert body["partial"] is True
    wellness = next(
        goal for goal in body["mission_result"]["goals"] if goal["goal_id"] == "wellness"
    )
    assert wellness["lifecycle"] == "UNCLEAR"
    assert wellness["value"] is None
    assert body["metadata"]["dialogue_state"]["consent_declined"] is False
    assert "wellness_unknown:Не знаю." in body["mission_result"]["observations"]


def test_unknown_does_not_suppress_later_real_red(
    session: CallSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _exhaust(session, "Не знаю.")
    _reply(session, "Я упала и не могу встать.")
    assert session.safety.active_risk == RiskLevel.RED
    assert session._engine is not None
    assert session._engine.state.safety_mode == "red"
    body = _public_result(session, monkeypatch)
    assert body["outcomes"]["family_status"] == "RED"
    assert body["outcomes"]["mission_status"] == "PARTIAL"
    assert body["observations"]
    assert any(
        event.event_type == "RED_SIGNAL"
        for event in session.store.get_events(session.state.call_id, session.state.family_id)
    )
    assert "wellness_unknown:Не знаю." in body["mission_result"]["observations"]


def test_unknown_note_does_not_displace_existing_observations(
    session: CallSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from packages.dialogue_engine.semantic_kernel.types import Observation

    _exhaust(session, "Не знаю.")
    assert session._engine is not None
    for index in range(40):
        session._engine.state.observations[f"obs-{index}"] = Observation(
            observation_id=f"obs-{index}",
            attribute=f"existing-{index}",
            value=f"value-{index}",
        )
    session._engine.state.observations["internal_marker"] = "not a public observation"
    body = _public_result(session, monkeypatch)
    notes = body["mission_result"]["observations"]
    assert notes == [
        *(f"existing-{index}:value-{index}" for index in range(40)),
        "wellness_unknown:Не знаю.",
    ]


def test_explicit_refusal_remains_a_distinct_call_outcome(
    session: CallSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(session, "Не хочу разговаривать.")
    assert session._engine is not None
    assert session._engine.state.call_closed
    assert session._engine.state.closing_reason == "revoke_consent"
    assert "wellness_unknown" not in session._engine.state.observations
    body = _public_result(session, monkeypatch)
    assert body["outcomes"]["call_outcome"] == "DECLINED"
    assert body["outcomes"]["family_status"] == "UNSET"
    assert not any(
        note.startswith("wellness_unknown:") for note in body["mission_result"]["observations"]
    )


def test_slot_declined_alone_is_not_consent_or_public_decline(
    session: CallSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = session._engine
    assert engine is not None
    engine.state.slots["wellness"] = SlotStatus.DECLINED
    engine.state.goals["wellness"].status = SlotStatus.DECLINED
    engine.state.goals["wellness"].lifecycle = GoalLifecycle.DECLINED
    engine.sync_to_legacy(session.state)
    assert session.state.slots["wellness"] == SlotStatus.DECLINED
    assert not session.state.consent_declined
    assert not session.state.call_revoked
    body = _public_result(session, monkeypatch)
    assert body["outcomes"]["call_outcome"] == "TECHNICAL"
    assert body["outcomes"]["family_status"] == "UNSET"
    assert body["termination_reason"] == TerminationReason.DISCONNECTED.value
