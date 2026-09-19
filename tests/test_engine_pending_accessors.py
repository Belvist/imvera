"""Cut 1+4c: engine pending_slot accessor contract (A.5.3).

The accessor powered the CallActor migration (proven vs mirror pre-4c).
Since Cut 4c the mirror is no longer synced on this path by design, so this
file now pins the accessor's direct contract: delivered → playing →
planned → next open slot.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

pytestmark = pytest.mark.dialogue_engine

FLOWS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("acc-good", ("Хорошо.", "Хорошее.", "Спал нормально.", "Дома.", "до свидания")),
    ("acc-bad", ("Плохо.", "Голова болит.", "Вчера началось.", "Ничего.", "до свидания")),
    ("acc-unclear", ("Не знаю.", "Абракадабра.", "Хорошо.", "Дома.", "до свидания")),
    ("acc-backchannel", ("Хорошо.", "ага", "Дома.", "до свидания")),
)


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
        family_id="acc-family",
        elder_display_name="Тест",
        store=InMemoryCallRecordStore(),
    )
    result = session.start()
    assert result.persist_ok, result.persist_error
    _deliver(session, result)
    _assert_accessor_parity(session)
    # Concrete checkpoint: opening asks wellness first.
    assert session._engine is not None
    assert session._engine.pending_slot_name() == "wellness"
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


def _assert_accessor_parity(session: CallSession) -> None:
    engine = session._engine
    assert engine is not None
    state = engine.state
    if state.delivered_question is not None:
        expected = state.delivered_question.slot
    elif state.playing_question is not None:
        expected = state.playing_question.slot
    elif state.planned_question is not None:
        expected = state.planned_question.slot
    else:
        expected = state.next_open_slot()
    assert engine.pending_slot_name() == expected


@pytest.mark.parametrize("call_id,texts", FLOWS)
def test_engine_accessors_match_synced_mirror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, call_id: str, texts: tuple[str, ...]
) -> None:
    session = _session(monkeypatch, tmp_path, call_id)
    engine = session._engine
    assert engine is not None
    for text in texts:
        uid = f"u-{session.turn_id + 1}"
        slot = engine.answer_context_slot()
        parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
        turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
        result = session.handle_user_text(text, utterance_id=uid, rich_turn=turn)
        _deliver(session, result)
        _assert_accessor_parity(session)
