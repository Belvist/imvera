"""Live fs-844600d2: «Нужна помощь?» + «Да» must escalate, never plain-close.

A RED clarify asks «правильно поняла? Нужна помощь?» — an affirmation
answers the help question with YES and must take the urgent path
(handoff), exactly like an explicit help request. A plain
«Поняла. Завершаю звонок.» on «да» abandons the elder mid-emergency.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


def test_yes_to_help_escalates_with_handoff() -> None:
    r = ScenarioRunner(call_id="help-yes", elder_display_name="Тест")
    result = r.run(
        [
            CallStarted(),
            "О, нет, сегодня что-то плохо себя чувствую так, прямо вообще ужас.",
            "Вот, знаешь, многое меня сейчас беспокоит",
            "Ой, чего много всего говорю болит у меня. У меня и голова болит, и сердце болит, всё болит у меня.",
            "А-да-да.",
            "Да говорю.",
        ]
    )
    assert r.state.call_closed
    texts = [e.text for e in result.speak_effects]
    assert texts, "must speak on close"
    # Urgent handoff, never the plain safety close.
    assert "Завершаю звонок" not in " ".join(texts)
    joined = " ".join(texts).lower()
    assert "передам" in joined or "близк" in joined


def test_unclear_answer_never_plain_closes_red() -> None:
    # A mumble that answers nothing must still handoff, never plain-close:
    # with head+heart pain on the table, silence cannot rule out emergency.
    r = ScenarioRunner(call_id="help-mumble", elder_display_name="Тест")
    result = r.run(
        [
            CallStarted(),
            "О, нет, сегодня что-то плохо себя чувствую так, прямо вообще ужас.",
            "Вот, знаешь, многое меня сейчас беспокоит",
            "Ой, чего много всего говорю болит у меня. У меня и голова болит, и сердце болит, всё болит у меня.",
            "Эээ.",
        ]
    )
    assert r.state.call_closed
    joined = " ".join(e.text for e in result.speak_effects)
    assert "Завершаю звонок" not in joined
    assert "передам" in joined.lower() or "близк" in joined.lower()
