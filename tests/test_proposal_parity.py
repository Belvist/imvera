"""Cut 4a parity: legacy-built vs engine-built TurnProposal (A.5.3).

Compares effect_to_proposal_legacy (mirror) vs effect_to_proposal (engine)
on session-level flows. All fields must match EXCEPT question_goal_id:
legacy uses random uuids per goal, engine uses slot-string ids (consumers
use them opaquely — wait-state keys, outbox records). The mapping change is
asserted explicitly, not hidden.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

pytestmark = pytest.mark.dialogue_engine

FLOWS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prop-good", ("Хорошо.", "Хорошее.", "Спал нормально.", "Дома.", "до свидания")),
    ("prop-bad", ("Плохо.", "Голова болит.", "Вчера началось.", "Ничего.", "до свидания")),
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
        family_id="prop-family",
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


def _compare_proposals(session: CallSession, speak) -> None:
    engine = session._engine
    assert engine is not None
    # Sync explicitly: production no longer syncs on this path (Cut 4a), so
    # the comparison needs identical inputs for both builders.
    engine.sync_to_legacy(session.state)
    # NOTE (Cut 4a): timer/wait proposals now carry the engine slot-rule
    # (same as speak proposals already did) instead of the legacy 7-check
    # rule. Proven inert: Validator short-circuits wait_for_continuation
    # with empty speech to allowed=True BEFORE the mandatory check
    # (validator.py), and no other consumer reads the wait-proposal field.
    # The commit-path partial still uses the 7-check parity rule.
    legacy_built = engine.effect_to_proposal_legacy(speak, session.turn_id, session.state)
    engine_built = engine.effect_to_proposal(speak, session.turn_id)
    assert engine_built.intent == legacy_built.intent
    assert engine_built.speech == legacy_built.speech
    assert engine_built.fsm_state == legacy_built.fsm_state
    assert engine_built.mandatory_remaining == legacy_built.mandatory_remaining
    assert engine_built.generation_id == legacy_built.generation_id
    if legacy_built.question_goal_id is None:
        assert engine_built.question_goal_id is None
    else:
        # Documented mapping change: uuid → slot-string, opaque downstream.
        assert engine_built.question_goal_id == speak.slot
        assert legacy_built.question_goal_id != engine_built.question_goal_id


@pytest.mark.parametrize("call_id,texts", FLOWS)
def test_proposal_parity_legacy_vs_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, call_id: str, texts: tuple[str, ...]
) -> None:
    session = _session(monkeypatch, tmp_path, call_id)
    engine = session._engine
    assert engine is not None
    for effect in list(engine.drain_speak_effects()):
        _compare_proposals(session, effect)
        engine.on_playout_started(effect.generation, effect.question_id)
        session.mark_spoken_action(effect.generation_id)
    for text in texts:
        uid = f"u-{session.turn_id + 1}"
        slot = engine.answer_context_slot()
        parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
        turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
        result = session.handle_user_text(text, utterance_id=uid, rich_turn=turn)
        if result.speak_effect is not None:
            _compare_proposals(session, result.speak_effect)
        for effect in result.followup_speak_effects:
            _compare_proposals(session, effect)
        _deliver(session, result)
