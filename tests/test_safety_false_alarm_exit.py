"""COMMIT 4: false-alarm engine exit (known semantic bug, separate patch).

RED → clarify → user says it was a false alarm → SafetySnapshot NONE but
the engine must also leave red handling and resume the suspended
obligation instead of safety-closing on the next substantive turn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.contracts.enums import AnswerJudgement, RiskLevel
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

pytestmark = pytest.mark.dialogue_engine


def _session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> CallSession:
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
        call_id="false-alarm",
        family_id="safety-family",
        elder_display_name="Тест",
        store=InMemoryCallRecordStore(),
    )
    result = session.start()
    assert result.persist_ok, result.persist_error
    _deliver(session, result)
    return session


def _deliver(session: CallSession, result: SessionTurnResult) -> None:
    assert result.persist_ok, result.persist_error
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


def test_false_alarm_exits_engine_red_handling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path)
    engine = session._engine
    assert engine is not None
    _rich_reply(session, "я упала и не могу встать")
    assert session.safety.active_risk == RiskLevel.RED
    assert engine.state.risk_handling is True
    episode = engine.state.risk_episode_id
    assert episode
    interp = UserInterpretation(
        judgement=AnswerJudgement.UNCLEAR, risk_false_alarm=True
    )
    result = session.handle_user_text("нет, это было про соседку", interp=interp)
    _deliver(session, result)
    assert session.safety.active_risk == RiskLevel.NONE
    # Engine must leave red handling (the bug: it stayed).
    assert engine.state.risk_handling is False
    assert engine.state.safety_mode == "none"
    # Next substantive turn must NOT safety-close; mission resumes.
    followup = _rich_reply(session, "Хорошо.")
    intents = [followup.proposal.intent]
    if followup.speak_effect is not None:
        intents.append(followup.speak_effect.intent)
    assert "safety_close" not in intents
    assert not engine.state.call_closed
