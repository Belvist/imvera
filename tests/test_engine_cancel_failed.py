"""COMMIT 2 (Cut 4d): failure/cancel engine ownership regression (A.5.3).

- effect_failed bumps revision, next turn works, stale effect dead;
- cancelled question: not delivered, attempts unchanged, reservation
  freed, retry possible, playing/planned/active cleared;
- no Planner calls on either engine path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue import planner as planner_module
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
        family_id="fail-family",
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


def _say_no_deliver(session: CallSession, text: str) -> SessionTurnResult:
    engine = session._engine
    assert engine is not None
    uid = f"u-{session.turn_id + 1}"
    slot = engine.answer_context_slot()
    parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
    turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
    return session.handle_user_text(text, utterance_id=uid, rich_turn=turn)


def _spy_planner(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    for name in (
        "release_question_attempt",
        "mark_question_delivered",
        "reserve_question_attempt",
    ):
        monkeypatch.setattr(
            planner_module.Planner,
            name,
            staticmethod(lambda *a, _n=name, **k: calls.append(_n)),
        )
    return calls


def test_cancel_clears_playout_without_delivery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path, "fail-cancel")
    engine = session._engine
    assert engine is not None
    calls = _spy_planner(monkeypatch)
    result = _say_no_deliver(session, "Хорошо.")
    assert result.speak_effect is not None
    fx = result.speak_effect
    engine.on_playout_started(fx.generation, fx.question_id)
    slot = fx.slot
    goal = engine.state.goals.get(slot) if slot else None
    attempts_before = goal.delivered_attempts if goal else 0
    assert engine.state.playing_question is not None
    assert engine.state.active_playout is not None
    session.cancel_playout_action(fx.generation_id)
    assert engine.state.playing_question is None
    assert engine.state.planned_question is None
    assert engine.state.active_playout is None
    # Cancel clears playing, not delivered history: the opening stays.
    assert engine.state.delivered_question is not None
    assert engine.state.delivered_question.intent == "opening_wellness"
    goal_after = engine.state.goals.get(slot) if slot else None
    if goal_after is not None:
        assert goal_after.delivered_attempts == attempts_before
        assert goal_after.reserved_question_id is None
    assert calls == []
    # Retry of the same slot works after cancel.
    retry = _say_no_deliver(session, "Хорошо.")
    assert retry.persist_ok, retry.persist_error


def test_effect_failed_keeps_dialogue_alive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _session(monkeypatch, tmp_path, "fail-effect")
    engine = session._engine
    assert engine is not None
    calls = _spy_planner(monkeypatch)
    rev_before = engine.revision
    session.handle_effect_failed("fx-dead", stage="TTS", error="boom")
    assert engine.revision > rev_before
    assert calls == []
    result = _say_no_deliver(session, "Хорошо.")
    assert result.persist_ok, result.persist_error
    _deliver(session, result)
