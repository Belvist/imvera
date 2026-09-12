"""Rich control obligations in DialogueEngine."""

from __future__ import annotations

import pytest

from packages.contracts.semantic import Evidence, SemanticPayload
from packages.dialogue_engine.effects import EndCallEffect
from packages.dialogue_engine.events import CallStarted, PlayoutCompleted, User
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.turn_understanding import (
    RichUserTurn,
    build_rich_turn_from_payload,
)

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


def _playout_hangup_after_final(runner: ScenarioRunner, speak) -> list:
    state, effects = reduce(
        runner.state,
        PlayoutCompleted(
            generation=speak.generation,
            question_id=speak.question_id,
            revision=runner.state.revision,
        ),
    )
    runner.state = state
    return effects


def test_stop_call_triggers_goodbye_confirm() -> None:
    """Explicit farewell / stop_call closes immediately (no double confirm)."""
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run([CallStarted(), _control_turn("stop_call", "до свидания")])
    intents = [e.intent for e in result.speak_effects]
    assert "goodbye_final" in intents
    assert "goodbye_confirm" not in intents
    assert result.state.call_closed


def test_wrong_person_closes_call() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run([CallStarted(), _control_turn("wrong_person", "не туда попали")])
    intents = [e.intent for e in result.speak_effects]
    assert "wrong_person_final" in intents
    assert result.state.call_closed


def test_wrong_person_final_emits_hangup_after_playout() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run([CallStarted(), _control_turn("wrong_person", "не туда попали")])
    speak = result.speak_effects[-1]
    assert speak.intent == "wrong_person_final"
    # ScenarioRunner completes hangup playout → EndCall already in result.effects
    assert any(isinstance(e, EndCallEffect) for e in result.effects)


def test_defer_closes_call() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run([CallStarted(), _control_turn("defer", "позже поговорим")])
    intents = [e.intent for e in result.speak_effects]
    assert "defer_final" in intents
    assert result.state.call_closed


def test_defer_final_emits_hangup_after_playout() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run([CallStarted(), _control_turn("defer", "позже поговорим")])
    speak = result.speak_effects[-1]
    assert speak.intent == "defer_final"
    assert any(isinstance(e, EndCallEffect) for e in result.effects)


def test_revoke_consent_closes_call() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run(
        [CallStarted(), _control_turn("revoke_consent", "не хочу разговаривать")]
    )
    intents = [e.intent for e in result.speak_effects]
    assert "revoke_consent_final" in intents
    assert result.state.call_closed


def test_revoke_consent_final_emits_hangup_after_playout() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run(
        [CallStarted(), _control_turn("revoke_consent", "не хочу разговаривать")]
    )
    speak = result.speak_effects[-1]
    assert speak.intent == "revoke_consent_final"
    assert any(isinstance(e, EndCallEffect) for e in result.effects)


def test_pause_sets_wait_timer() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    result = runner.run([CallStarted(), "Хорошо.", _control_turn("pause", "подождите")])
    assert any(e.kind == "timer" for e in result.effects)


def test_stop_call_wins_over_backchannel() -> None:
    runner = ScenarioRunner(call_id="ctrl", elder_display_name="Тест")
    runner.run([CallStarted(), "Хорошо."])
    turn = RichUserTurn(
        utterance_id="u-mix",
        raw_text="угу, всё, до свидания",
        dialogue_act="backchannel",
        control="stop_call",
        answers_pending_question=False,
        needs_clarification=False,
    )
    result = runner.run([User(text=turn.raw_text, rich_turn=turn)])
    intents = [e.intent for e in result.speak_effects]
    assert "goodbye_final" in intents
    assert "goodbye_confirm" not in intents
    assert result.state.call_closed
    assert not any(e.kind == "timer" for e in result.effects)
