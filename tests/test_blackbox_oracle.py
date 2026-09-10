"""External oracle intent matching — no SIP required."""

from __future__ import annotations

from tools.blackbox_caller.oracle import (
    analyze_transcript,
    evaluate_scenario_expectations,
)


def test_opening_and_mood_intents_detected() -> None:
    text = (
        "Здравствуйте. Это сервис Амвера. Даниил, Как вы себя чувствуете? "
        "А какое у вас сегодня настроение?"
    )
    assertions = analyze_transcript(text)
    assert "opening" in assertions.observed_intents
    assert "check_mood" in assertions.observed_intents
    assert assertions.opening_count == 1


def test_multi_slot_forbidden_reask() -> None:
    text = (
        "Здравствуйте. Как вы себя чувствуете? "
        "Понимаю. А какое настроение? "
        "Как вы спали? "
        "Спасибо за разговор."
    )
    assertions = analyze_transcript(text, scenario_tags=["multi_slot"])
    assert assertions.forbidden_sleep_reask
    ok, errors = evaluate_scenario_expectations(
        assertions,
        ["opening", "check_mood", "summary"],
    )
    assert not ok
    assert errors


def test_goodbye_and_summary() -> None:
    text = "Спасибо за разговор. До свидания, хорошего дня."
    assertions = analyze_transcript(text)
    assert assertions.reached_summary
    assert assertions.reached_goodbye


def test_ack_bad_phrase() -> None:
    text = "Мне жаль это слышать. А какое у вас настроение?"
    assertions = analyze_transcript(text)
    assert "ack_bad" in assertions.observed_intents
