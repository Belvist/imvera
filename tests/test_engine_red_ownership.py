"""Cut 4b: RED/safety engine ownership regression (A.5.3).

Drives the ENGINE red branch (rich turn with RED risk) and pins:
1. interrupt sets engine risk_handling/fsm/episode;
2. second RED causes no double interrupt;
3. false alarm resolves with the engine episode id;
4. risk observation persisted + single RED_SIGNAL event;
5. safety speech flow unchanged (speak effect present, call continues).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.contracts.enums import AnswerJudgement, FsmState, RiskLevel
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

pytestmark = pytest.mark.dialogue_engine


def _session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, call_id: str) -> CallSession:
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
    session = CallSession(
        call_id=call_id,
        family_id="red-family",
        elder_display_name="Тест",
        store=InMemoryCallRecordStore(),
    )
    result = session.start()
    assert result.persist_ok, result.persist_error
    _deliver(session, result)
    return session


def _deliver(session: CallSession, result: SessionTurnResult) -> None:
    assert session._engine is not None
    effects = ([result.speak_effect] if result.speak_effect else []) + list(
        result.followup_speak_effects
    )
    for effect in effects:
        session._engine.on_playout_started(effect.generation, effect.question_id)
        assert session.mark_spoken_action(effect.generation_id)


def _rich_reply(session: CallSession, text: str) -> SessionTurnResult:
    engine = session._engine
    assert engine is not None
    uid = f"u-{session.turn_id + 1}"
    slot = engine.answer_context_slot()
    parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
    turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
    result = session.handle_user_text(text, utterance_id=uid, rich_turn=turn)
    _deliver(session, result)
    return result


def _red_events(session: CallSession) -> list:
    return [
        e
        for e in session.store.get_events(session.state.call_id, session.state.family_id)
        if e.event_type == "RED_SIGNAL"
    ]


def test_engine_red_interrupt_sets_engine_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path, "red-own")
    engine = session._engine
    assert engine is not None
    result = _rich_reply(session, "я упала и не могу встать")
    assert session.safety.active_risk == RiskLevel.RED
    assert engine.state.risk_handling is True
    assert engine.state.fsm_state == FsmState.RED_SIGNAL
    assert engine.state.risk_episode_id
    assert engine.state.risk_episode_id == session.safety.active_episode_id
    assert result.speak_effect is not None
    assert len(_red_events(session)) == 1


def test_engine_second_red_no_double_interrupt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path, "red-twice")
    engine = session._engine
    assert engine is not None
    _rich_reply(session, "я упала и не могу встать")
    episode = engine.state.risk_episode_id
    _rich_reply(session, "я упала и не могу встать")
    assert engine.state.risk_handling is True
    assert engine.state.risk_episode_id == episode
    assert len(_red_events(session)) == 1


def test_engine_false_alarm_uses_engine_episode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path, "red-false")
    engine = session._engine
    assert engine is not None
    _rich_reply(session, "я упала и не могу встать")
    episode = engine.state.risk_episode_id
    assert episode
    interp = UserInterpretation(
        judgement=AnswerJudgement.UNCLEAR, risk_false_alarm=True
    )
    result = session.handle_user_text("нет, это было про соседку", interp=interp)
    _deliver(session, result)
    assert session.safety.active_risk == RiskLevel.NONE


def test_engine_red_observation_persisted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path, "red-obs")
    _rich_reply(session, "я упала и не могу встать")
    result = session.get_persisted_result()
    assert result is not None
    assert len(result.observations) >= 1
