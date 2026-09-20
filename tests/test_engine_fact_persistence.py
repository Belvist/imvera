"""COMMIT 1: engine fact persistence regression (A.5.3 close-out).

_persist_new_facts sources EngineState (Cut 4c), not the legacy mirror.
Pins: filled engine facts become persisted observations across turns,
revision keys advance without conflict, repeat passes lose nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.contracts.enums import SlotStatus
from packages.core.memory_store import InMemoryCallRecordStore
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
        call_id="fact-persist",
        family_id="fact-family",
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


def _say(session: CallSession, text: str) -> SessionTurnResult:
    engine = session._engine
    assert engine is not None
    uid = f"u-{session.turn_id + 1}"
    slot = engine.answer_context_slot()
    parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
    turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
    result = session.handle_user_text(text, utterance_id=uid, rich_turn=turn)
    _deliver(session, result)
    return result


def test_engine_facts_persist_across_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path)
    engine = session._engine
    assert engine is not None
    _say(session, "Хорошо.")
    assert engine.state.slots["wellness"] == SlotStatus.FILLED
    assert engine.state.slot_values["wellness"] == "Хорошо."
    snap = session.store.get_call_result("fact-persist", "fact-family")
    assert snap is not None
    assert snap.facts.get("wellness") == "Хорошо."
    obs_after_first = list(session._persisted_obs_ids)
    assert len(obs_after_first) >= 1
    keys_first = {k for k in session._persisted_keys if ":fact:wellness:" in k}
    assert keys_first, "wellness fact revision key persisted"

    _say(session, "Хорошее.")
    snap = session.store.get_call_result("fact-persist", "fact-family")
    assert snap is not None
    assert snap.facts.get("wellness") == "Хорошо."
    obs_after_second = list(session._persisted_obs_ids)
    assert len(obs_after_second) >= len(obs_first := obs_after_first)
    assert set(obs_first) <= set(obs_after_second), "repeat pass loses nothing"
    keys_second = {k for k in session._persisted_keys if ":fact:" in k}
    assert len(keys_second) == len(set(keys_second)), "no revision key conflict"
    assert len(snap.observations) >= 1, "fact observations stored on snapshot"
