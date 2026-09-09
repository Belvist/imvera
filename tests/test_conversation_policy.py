"""Conversation policy obligations."""

from __future__ import annotations

from packages.dialogue_engine.conversation_policy import (
    ConversationObligation,
    decide_conversation_policy,
)
from packages.dialogue_engine.issue_memory import ingest_rich_turn
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text


def test_user_question_obligation() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    turn = build_rich_turn_from_text("А кто вы?", utterance_id="u-1")
    decision = decide_conversation_policy(state, turn)
    assert decision is not None
    assert decision.obligation == ConversationObligation.ANSWER_USER_QUESTION
    assert "Вера" in decision.text


def test_correction_acknowledges_history() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    ingest_rich_turn(
        state,
        build_rich_turn_from_text("Живот болит.", utterance_id="u-0"),
    )
    turn = build_rich_turn_from_text("Я же говорил, живот болит.", utterance_id="u-1")
    decision = decide_conversation_policy(state, turn)
    assert decision is not None
    assert decision.obligation == ConversationObligation.HANDLE_CORRECTION
    assert "говорили" in decision.text.lower()


def test_headache_first_question_not_abdominal() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    turn = build_rich_turn_from_text(
        "Состояние не очень, голова болит и тошнит.",
        utterance_id="u-1",
    )
    ingest_rich_turn(state, turn)
    decision = decide_conversation_policy(state, turn)
    assert decision is not None
    assert "живот" not in decision.text.lower()
    assert "голов" in decision.text.lower()
