"""Parity harness: engine-native projection vs legacy snapshot (ADR-019).

Decision (b): legacy-compatible surface must match verbatim; store-owned
metadata keys are excluded by design (see STORE_OWNED_METADATA_KEYS).
Any field drift outside the exclusion set fails the cut.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue_engine.persistence_projection import (
    STORE_OWNED_METADATA_KEYS,
    project_call_result,
)
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

pytestmark = pytest.mark.dialogue_engine

FLOWS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("parity-good", ("Хорошо.", "Хорошее.", "Спал нормально.", "Дома.", "до свидания")),
    ("parity-bad", ("Плохо.", "Голова болит.", "Вчера началось.", "Ничего.", "до свидания")),
    ("parity-so-so", ("Так себе.", "Голова болит.", "Вчера началось.", "Ничего.", "до свидания")),
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
        family_id="parity-family",
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


def _run_flow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, call_id: str, texts: tuple[str, ...]
) -> CallSession:
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
    return session


def _assert_parity(session: CallSession) -> None:
    assert session._engine is not None
    # Compare against what store.finalize_call receives: _snapshot() with the
    # call_ended envelope applied (session._finalize_call_if_needed).
    assert session.state.final_action_done and not session.state.call_finalized
    legacy = session._snapshot().model_copy(update={"call_ended": True})
    projected = project_call_result(
        session._engine,
        call_id=session.state.call_id,
        family_id=session.state.family_id,
        elder_display_name=session.state.elder_display_name,
        observation_ids=list(session._persisted_obs_ids),
        mission_is_daily_check=session.mission.is_daily_check,
        legacy_public_status=(
            session.state.public_status.value
            if getattr(session.state, "public_status", None)
            else None
        ),
    )
    assert projected.facts == legacy.facts
    assert projected.fact_quotes == legacy.fact_quotes
    assert projected.fsm_state == legacy.fsm_state
    assert projected.partial == legacy.partial
    assert projected.call_ended == legacy.call_ended
    assert projected.termination_reason == legacy.termination_reason
    assert projected.mission_result == legacy.mission_result
    assert projected.outcomes == legacy.outcomes
    legacy_meta = {
        k: v for k, v in legacy.metadata.items() if k not in STORE_OWNED_METADATA_KEYS
    }
    projected_meta = {
        k: v for k, v in projected.metadata.items() if k not in STORE_OWNED_METADATA_KEYS
    }
    assert projected_meta == legacy_meta


@pytest.mark.parametrize("call_id,texts", FLOWS)
def test_projection_matches_legacy_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, call_id: str, texts: tuple[str, ...]
) -> None:
    session = _run_flow(monkeypatch, tmp_path, call_id, texts)
    _assert_parity(session)
