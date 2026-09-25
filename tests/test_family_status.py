"""P0#4: family status wired via StatusEngine (audit order).

A normally completed daily check must resolve GREEN/YELLOW, never UNSET.
RED safety path keeps RED.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
        family_id="status-family",
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


def test_completed_check_resolves_green_or_yellow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path, "status-ok")
    engine = session._engine
    assert engine is not None
    for text in ("Хорошо.", "Хорошее.", "Спал нормально.", "Дома.", "до свидания"):
        uid = f"u-{session.turn_id + 1}"
        slot = engine.answer_context_slot()
        parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
        turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
        result = session.handle_user_text(text, utterance_id=uid, rich_turn=turn)
        _deliver(session, result)
    snap = session._snapshot()
    assert snap.outcomes is not None
    assert snap.outcomes.candidate_family_status in ("GREEN", "YELLOW")
    assert snap.outcomes.candidate_family_status != "UNSET"
    got = snap.metadata["outcomes"]["candidate_family_status"]
    assert got == snap.outcomes.candidate_family_status


def test_red_keeps_red_candidate_family_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path, "status-red")
    engine = session._engine
    assert engine is not None
    engine.state.safety_mode = "red"
    engine.state.risk_handling = True
    snap = session._snapshot()
    assert snap.outcomes is not None
    assert snap.outcomes.candidate_family_status == "RED"


def _completed_suffering_engine(call_id: str):
    """Default mission COMPLETED, but the elder complained (fs-1b34dc2b shape)."""
    from packages.contracts.enums import FsmState
    from packages.dialogue_engine.engine import DialogueEngine
    from packages.dialogue_engine.policy import apply_slot_answer
    from packages.dialogue_engine.state import GoalLifecycle

    engine = DialogueEngine(call_id=call_id, elder_display_name="Тест")
    engine.start()
    for slot, val in (
        ("wellness", "Всё болит"),
        ("mood", "Плохо"),
        ("sleep", "Не спал"),
        ("plans", "Дома"),
    ):
        apply_slot_answer(
            engine.state, slot, val, turn_id="t1", source_text=val, confidence=0.9
        )
    for goal in engine.state.goals.values():
        goal.lifecycle = GoalLifecycle.SATISFIED
    engine.state.call_closed = True
    engine.state.fsm_state = FsmState.FINAL_CLASSIFICATION
    return engine


def test_open_complaint_floors_completed_mission_to_yellow() -> None:
    from packages.dialogue_engine.mission_result import (
        build_call_outcomes,
        build_mission_result,
    )
    from packages.dialogue_engine.state import IssueEpisode

    engine = _completed_suffering_engine("status-suffer")
    assert build_mission_result(engine.state).status == "COMPLETED"
    engine.state.issue_episodes["ep-1"] = IssueEpisode(
        episode_id="ep-1",
        primary_label="голова болит",
        kind="issue",
        subject="speaker",
        status="open",
    )
    assert build_call_outcomes(engine.state).candidate_family_status == "YELLOW"


def test_probed_concern_floors_completed_mission_to_yellow() -> None:
    from packages.dialogue_engine.mission_result import build_call_outcomes

    engine = _completed_suffering_engine("status-concern")
    engine.state.wellness_concern = "тошнит"
    assert build_call_outcomes(engine.state).candidate_family_status == "YELLOW"


def test_resolved_or_other_person_complaint_keeps_green() -> None:
    from packages.dialogue_engine.mission_result import build_call_outcomes
    from packages.dialogue_engine.state import IssueEpisode

    engine = _completed_suffering_engine("status-resolved")
    engine.state.issue_episodes["ep-1"] = IssueEpisode(
        episode_id="ep-1",
        primary_label="голова болит",
        kind="issue",
        subject="speaker",
        status="resolved",
    )
    engine.state.issue_episodes["ep-2"] = IssueEpisode(
        episode_id="ep-2",
        primary_label="нога болит",
        kind="issue",
        subject="other_person",
        status="open",
    )
    assert build_call_outcomes(engine.state).candidate_family_status == "GREEN"
