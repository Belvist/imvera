"""Cut 4a insurance: engine timer/wait path regression (A.5.3).

Covers the new ensure_goal() in the timer branch: question delivered →
backchannel → TimerEffect → wait_for_continuation with the same slot/goal
→ timer expiry re-asks → no spurious goals created.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
        call_id="timer-wait",
        family_id="timer-family",
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


def test_backchannel_timer_wait_same_slot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session = _session(monkeypatch, tmp_path)
    engine = session._engine
    assert engine is not None
    goals_before = set(engine.state.goals)
    uid = f"u-{session.turn_id + 1}"
    slot = engine.answer_context_slot()
    parsed = interpret("ага", utterance_id=uid, engine_state=engine.state, answer_slot=slot)
    turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
    result = session.handle_user_text("ага", utterance_id=uid, rich_turn=turn)
    assert result.timer_effect is not None, "expected backchannel TimerEffect"
    assert result.proposal.intent == "wait_for_continuation"
    assert result.proposal.speech == ""
    assert result.validated.allowed
    waiting = engine.state.waiting_on_slot
    assert waiting, "engine must hold the waited slot"
    assert result.proposal.wait_goal_id == (engine.state.goals[waiting].goal_id or waiting)
    # No spurious goals from the timer branch ensure_goal().
    assert set(engine.state.goals) - goals_before <= {waiting}
    expired = session.handle_wait_expired(result.timer_effect.effect_id)
    assert expired.persist_ok, expired.persist_error
    assert expired.speak_effect is not None or expired.proposal.intent in (
        "wait_for_continuation",
        "clarify_wellness",
        "check_sleep",
        "check_mood",
        "check_plans",
        "important_to_share",
    )
