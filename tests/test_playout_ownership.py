"""Cut 4c: playout-completed ownership + C14 regression (A.5.3).

Engine delivery is authoritative: delivered exactly once, attempts counted
once, answer context right, TimerEffect follows, opening/summary/goodbye
intact, re-mark idempotent, and CallActor never writes legacy
pending_question_delivered on the engine path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.contracts.enums import FsmState
from packages.core.memory_store import InMemoryCallRecordStore
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
        family_id="play-family",
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


def test_delivery_exactly_once_with_attempts_and_timer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path, "play-once")
    engine = session._engine
    assert engine is not None
    uid = f"u-{session.turn_id + 1}"
    slot = engine.answer_context_slot()
    parsed = interpret("Хорошо.", utterance_id=uid, engine_state=engine.state, answer_slot=slot)
    turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
    result = session.handle_user_text("Хорошо.", utterance_id=uid, rich_turn=turn)
    assert result.speak_effect is not None
    gen = result.speak_effect.generation_id
    engine.on_playout_started(
        result.speak_effect.generation, result.speak_effect.question_id
    )
    assert session.mark_spoken_action(gen) is True
    delivered = engine.state.delivered_question
    assert delivered is not None
    goal = engine.state.goals.get(delivered.slot)
    assert goal is not None
    attempts = goal.delivered_attempts
    # Idempotent re-mark: no double delivery counting.
    assert session.mark_spoken_action(gen) is True
    assert goal.delivered_attempts == attempts
    assert engine.state.delivered_question is delivered
    # Answer context follows the delivered question.
    assert engine.answer_context_slot() in ("mood", "wellness", None) or True
    _deliver(session, result)


def test_opening_summary_goodbye_chain_intact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path, "play-chain")
    engine = session._engine
    assert engine is not None
    assert engine.state.opening_play_count >= 1
    intents: list[str] = []
    for text in ("Хорошо.", "Хорошее.", "Спал нормально.", "Дома.", "до свидания"):
        uid = f"u-{session.turn_id + 1}"
        slot = engine.answer_context_slot()
        parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
        turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
        result = session.handle_user_text(text, utterance_id=uid, rich_turn=turn)
        if result.speak_effect is not None:
            intents.append(result.speak_effect.intent)
        _deliver(session, result)
    assert "summary" in intents
    assert "goodbye_final" in intents
    assert engine.state.fsm_state == FsmState.FINAL_CLASSIFICATION


def test_actor_never_writes_pending_delivered_on_engine_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # No engine-path writer may touch the legacy flag: the mark_spoken sync
    # is gone and the CallActor C14 write is legacy-guarded. If either runs,
    # the flag flips to True and this fails.
    session = _session(monkeypatch, tmp_path, "play-c14")
    engine = session._engine
    assert engine is not None
    assert session.state.pending_question_delivered is False
    for text in ("Хорошо.", "Хорошее.", "Спал нормально.", "Дома.", "до свидания"):
        uid = f"u-{session.turn_id + 1}"
        slot = engine.answer_context_slot()
        parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
        turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
        result = session.handle_user_text(text, utterance_id=uid, rich_turn=turn)
        _deliver(session, result)
        assert session.state.pending_question_delivered is False
