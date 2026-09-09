"""Rich control obligations in DialogueEngine."""

from __future__ import annotations

import pytest

from packages.contracts.semantic import Evidence, SemanticPayload
from packages.dialogue_engine.events import CallStarted, User
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_payload

pytestmark = pytest.mark.dialogue_engine


def _control_turn(control: str, text: str) -> User:
    payload = SemanticPayload(
        dialogue_act="answer",
        control=control,
        control_evidence=Evidence(start=0, end=len(text), quote=text),
        consent_answer="not_applicable",
        answers_pending_question=False,
        needs_clarification=False,
    )
    return User(
        text=text,
        rich_turn=build_rich_turn_from_payload(
            payload,
            utterance_id="u-control",
            raw_text=text,
        ),
    )


def test_stop_call_triggers_goodbye_confirm() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run([CallStarted(), _control_turn("stop_call", "до свидания")])
    intents = [e.intent for e in result.speak_effects]
    assert "goodbye_confirm" in intents


def test_wrong_person_closes_call() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run([CallStarted(), _control_turn("wrong_person", "не туда попали")])
    intents = [e.intent for e in result.speak_effects]
    assert "wrong_person_final" in intents
    assert result.state.call_closed


def test_defer_closes_call() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run([CallStarted(), _control_turn("defer", "позже поговорим")])
    intents = [e.intent for e in result.speak_effects]
    assert "defer_final" in intents
    assert result.state.call_closed


def test_pause_sets_wait_timer() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run([CallStarted(), "Хорошо.", _control_turn("pause", "подождите")])
    assert any(e.kind == "timer" for e in result.effects)
