"""Free-speech regression — not scripted fs-592."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.issue_memory import has_abdominal_episode
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="free-speech", elder_display_name="Тест")


def test_headache_nausea_no_abdominal_question() -> None:
    runner = _runner()
    runner.run([CallStarted()])
    result = runner.run(
        ["Состояние не очень, голова болит и тошнит."],
    )
    intents = [e.intent for e in result.speak_effects]
    assert "topic_abdominal_pain_current" not in intents
    assert not has_abdominal_episode(result.state)
    assert any(
        "headache" in i or "голов" in e.text.lower()
        for i, e in zip(intents, result.speak_effects, strict=False)
    )

    result = runner.run(["С 10 утра."])
    result = runner.run(["Сильная."])
    intents = [e.intent for e in result.speak_effects]
    texts = " ".join(e.text.lower() for e in result.speak_effects)
    assert "topic_abdominal_pain_current" not in intents
    assert "живот" not in texts


def test_user_question_then_resume() -> None:
    runner = _runner()
    runner.run([CallStarted(), "Плохо спал."])
    result = runner.run(["А вы кто вообще?"])
    texts = " ".join(e.text for e in result.speak_effects)
    assert "Вера" in texts


def test_correction_not_dumb_repeat() -> None:
    runner = _runner()
    runner.run([CallStarted(), "Живот болит."])
    result = runner.run(["Я же говорил, живот болит."])
    texts = " ".join(e.text.lower() for e in result.speak_effects)
    assert "говорили" in texts


def test_requires_rich_not_fast_bypass() -> None:
    from packages.dialogue_engine.issue_mention_extract import requires_rich_interpretation

    assert requires_rich_interpretation("Голова болит и тошнит.")
    assert requires_rich_interpretation("Я же говорил, сердце с утра болит.")
    assert not requires_rich_interpretation("угу")
