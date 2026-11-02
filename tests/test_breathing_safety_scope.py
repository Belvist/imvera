"""Current breathing difficulty is urgent; denial/history/another person is not.

Exercise both existing detectors and the actual rich/semantic reducer funnels.
These are source-level safety regressions, not real STT or family delivery proof.
"""
from __future__ import annotations

import pytest

from packages.dialogue_engine.check_path import is_urgent_action
from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import UserTurnReceived
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
from packages.dialogue_engine.state import CheckPath
from packages.safety.rules import match_deterministic_signals

pytestmark = pytest.mark.dialogue_engine

CURRENT = [
    "Мне сейчас трудно дышать.", "Мне тяжело дышать.", "Трудно дышать.",
    "Дышать тяжело.", "Сейчас дышать трудно.",
    "Вчера было трудно дышать, а сейчас тоже трудно дышать.",
]
EXCLUDED = [
    "Мне не трудно дышать.", "Дышать не тяжело.",
    "Мне сейчас не тяжело дышать.", "Вчера было трудно дышать.",
    "Раньше мне было тяжело дышать.", "Вчера было трудно дышать, сейчас всё хорошо.",
    "У мужа трудно дышать.", "Мужу тяжело дышать.",
    "Дочери сейчас трудно дышать.", "Соседке тяжело дышать.",
    "Ему трудно дышать.", "Ей сейчас тяжело дышать.",
]


@pytest.mark.parametrize("text", CURRENT)
def test_current_breathing_difficulty_reaches_both_detectors(text):
    assert is_urgent_action(text)
    assert "breathing" in match_deterministic_signals(text)


@pytest.mark.parametrize("text", EXCLUDED)
def test_scoped_out_breathing_difficulty_is_not_speaker_emergency(text):
    assert not is_urgent_action(text)
    assert "breathing" not in match_deterministic_signals(text)


@pytest.mark.parametrize("prior", [None, "Голова болит.", "Вчера дочь приезжала."])
def test_breathing_difficulty_interrupts_rich_conversation(prior):
    engine = DialogueEngine(call_id="breathing", elder_display_name="Тест")
    engine.start()
    if prior:
        engine.on_user_turn(turn_id="u1", text=prior,
                            rich_turn=engine.build_rich_turn(prior, utterance_id="u1"))
    engine.on_user_turn(turn_id="u2", text=CURRENT[0],
                        rich_turn=engine.build_rich_turn(CURRENT[0], utterance_id="u2"))
    assert engine.state.check_path == CheckPath.URGENT
    assert engine.state.closing_reason == "urgent"
    assert engine.state.call_closed
    assert any(isinstance(e, SpeakEffect) and e.intent == "urgent_close"
               for e in engine.drain_speak_effects())


def test_breathing_difficulty_interrupts_semantic_funnel():
    engine = DialogueEngine(call_id="breathing-semantic", elder_display_name="Тест")
    engine.start()
    semantic = SemanticTurn(act=SemanticAct.ANSWER, target_slot="wellness",
                            value="negative", source_quote=CURRENT[0])
    state, effects = reduce(engine.state, UserTurnReceived(
        turn_id="u1", text=CURRENT[0], semantic=semantic, revision=engine.state.revision,
    ))
    assert state.check_path == CheckPath.URGENT
    assert state.closing_reason == "urgent"
    assert any(isinstance(e, SpeakEffect) and e.intent == "urgent_close" for e in effects)


def test_live_session_path_persists_breathing_signal_with_original_quote(monkeypatch, tmp_path):
    from packages.contracts.enums import RiskLevel
    from packages.core.memory_store import InMemoryCallRecordStore
    from packages.dialogue.session import CallSession
    from packages.dialogue_engine import caller_memory

    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")
    monkeypatch.setattr(caller_memory, "_store_dir", lambda: tmp_path / "phrases")
    store = InMemoryCallRecordStore()
    session = CallSession(call_id="breathing-session", family_id="test-family",
                          elder_display_name="Тест", store=store)
    session.start()
    turn = session._engine.build_rich_turn(CURRENT[0], utterance_id="u1")
    result = session.handle_user_text(CURRENT[0], utterance_id="u1", rich_turn=turn)
    assert result.persist_ok
    assert result.safety.active_risk == RiskLevel.RED
    # CallSession deliberately asks one safety confirmation for a descriptive
    # RED interrupt; the raw SDK funnel instead emits urgent_close directly.
    # Neither is an ordinary wellness probe. Do not silently change that owner.
    assert result.speak_effect.intent == "safety_clarify"
    assert session._engine.state.risk_handling
    events = store.get_events(session.state.call_id, "test-family")
    red = [event for event in events if event.event_type == "RED_SIGNAL"]
    assert len(red) == 1 and red[0].payload["quote"] == CURRENT[0]
    risks = [obs for obs in store._observations[session.state.call_id]
             if obs.risk_level == RiskLevel.RED]
    assert len(risks) == 1 and risks[0].source_quote == CURRENT[0]
    # Persisted observations/events are not a delivered family notification.
