"""Urgent speech cannot substitute for a Core/family delivery receipt."""

import pytest

from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.state import CheckPath

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize("text", ["Мне сейчас трудно дышать.", "Не могу дышать."])
def test_urgent_sdk_retains_signal_and_gives_help_route_without_delivery_claim(monkeypatch, text):
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")
    engine = DialogueEngine(call_id="no-family-receipt")
    engine.start()
    while (speech := engine.pop_speak_effect()) is not None:
        engine.on_playout_completed(speech.generation, speech.question_id)
    engine.on_user_turn(
        "urgent", text, rich_turn=engine.build_rich_turn(text, utterance_id="urgent")
    )
    speech = []
    while (effect := engine.pop_speak_effect()) is not None:
        speech.append(effect)
    spoken = " ".join(s.text for s in speech).lower()
    assert engine.state.check_path == CheckPath.URGENT
    assert "передам" not in spoken and "отправила" not in spoken
    assert "112" in spoken and "близк" in spoken
    assert any(s.intent == "urgent_close" for s in speech)
