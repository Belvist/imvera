"""Production contract: engine-native snapshot on the engine path (ADR-019).

Since the cutover, `CallSession._snapshot()` builds from EngineState via
`project_call_result`. These tests pin the persisted contract on closed
calls: verbatim facts/quotes (decision b), final FSM, COMPLETED termination,
store-owned metadata survival (Postgres replaces metadata wholesale).

Pre-cutover projection-vs-legacy parity evidence lives at ebff322 CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.contracts.core import TerminationReason
from packages.contracts.enums import FsmState
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

pytestmark = pytest.mark.dialogue_engine

FLOWS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("proj-good", ("Хорошо.", "Хорошее.", "Спал нормально.", "Дома.", "до свидания")),
    ("proj-bad", ("Плохо.", "Голова болит.", "Вчера началось.", "Ничего.", "до свидания")),
    ("proj-so-so", ("Так себе.", "Голова болит.", "Вчера началось.", "Ничего.", "до свидания")),
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
        family_id="proj-family",
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


@pytest.mark.parametrize("call_id,texts", FLOWS)
def test_production_snapshot_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, call_id: str, texts: tuple[str, ...]
) -> None:
    session = _run_flow(monkeypatch, tmp_path, call_id, texts)
    assert session._engine is not None
    assert session._engine.state.call_closed
    snap = session._snapshot()
    assert snap.call_id == call_id
    assert snap.fsm_state == FsmState.FINAL_CLASSIFICATION
    assert snap.termination_reason == TerminationReason.COMPLETED
    assert snap.call_ended is True
    # Q0.1 evidence: quotes pair with the CURRENT value (correction flows
    # may hold a later record — never fabricate evidence).
    assert session._engine is not None
    records = session._engine.state.slot_records
    assert set(snap.fact_quotes) == set(snap.facts)
    for slot, value in snap.facts.items():
        record = records.get(slot)
        if record is not None and record.value == value and record.source_text:
            expected = record.source_text
        else:
            expected = value
        assert snap.fact_quotes[slot] == expected
    assert snap.facts.get("wellness")
    assert len(snap.observations) > 0
    assert snap.mission_result is not None
    assert snap.outcomes is not None
    assert "mission_result" in snap.metadata
    assert "outcomes" in snap.metadata


def test_store_owned_metadata_survives_production_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Postgres replaces metadata wholesale at finalize; InMemory merges.

    Seeded store-owned/unknown keys must survive the production snapshot.
    """
    session = _run_flow(monkeypatch, tmp_path, "proj-binding", FLOWS[0][1])
    store = session.store
    seeded = {
        "product_call_binding": {"call_id": "proj-binding", "trunk": "lab"},
        "custom_unknown": "keep-me",
    }
    snap = store.get_call_result("proj-binding", "proj-family")
    assert snap is not None
    store.save_dialogue_snapshot(
        snap.model_copy(update={"metadata": {**snap.metadata, **seeded}}),
        "proj-family",
    )
    final = session._snapshot()
    for key, value in seeded.items():
        assert final.metadata[key] == value
    assert "action_outbox" in final.metadata
