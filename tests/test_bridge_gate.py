"""Cut 1 gate: composer-written bridges are validated, fallback is byte-identical."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.dialogue_engine


def test_accept_paraphrase() -> None:
    from packages.voice_runtime.bridge_gate import validate_bridge

    ok, reason = validate_bridge(
        "Сочувствую, боль действительно сильная",
        original_bridge="Поняла вас. Боль сильная или терпимая?",
        user_text="Сильно болит голова.",
    )
    assert ok, reason


def test_accept_identical_to_original() -> None:
    from packages.voice_runtime.bridge_gate import validate_bridge

    orig = "Поняла вас. Головная боль — зафиксировала."
    ok, reason = validate_bridge(orig, original_bridge=orig, user_text="Голова болит.")
    assert ok, reason


def test_reject_measured_qwen_improvisation() -> None:
    from packages.voice_runtime.bridge_gate import validate_bridge

    # Measured :9103 output for user «Сильно болит»: adds a move + misspells.
    ok, reason = validate_bridge(
        "Понимаю, сильная боль — это тяжело. Нужно проверить, как вы чувствуетесь.",
        original_bridge="Понимаю, сильная боль — это тяжело.",
        user_text="Сильно болит.",
    )
    assert not ok and reason == "extra_move", reason


def test_reject_question_promise_verdict_ask() -> None:
    from packages.voice_runtime.bridge_gate import validate_bridge

    kw = {
        "original_bridge": "Поняла вас. Живот болит — зафиксировала.",
        "user_text": "Живот болит.",
    }
    for bad, why in [
        ("Поняла вас, а что ещё болит?", "has_question_mark"),
        ("Поняла, я вызову скорую.", "promise"),
        ("Всё хорошо, статус зелёный.", "verdict"),
        ("Скажите подробнее про живот.", "ask_verb"),
        ("", "empty"),
        ("Поняла " * 30, "too_long"),
        ("Understood, noted.", "not_russian"),
    ]:
        ok, reason = validate_bridge(bad, **kw)
        assert not ok, (bad, reason)
        assert reason == why, (bad, reason)


def test_reject_parrot_of_last_vera_line() -> None:
    from packages.voice_runtime.bridge_gate import validate_bridge

    ok, reason = validate_bridge(
        "поняла вас. живот болит — зафиксировала.",
        original_bridge="Другое начало про живот.",
        user_text="Живот болит.",
        last_vera_line="Поняла вас. Живот болит — зафиксировала.",
    )
    assert not ok and reason == "parrot"
