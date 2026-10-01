"""Live-call defects fs-a7c4e0df/fs-74b8f8ce (2026-10-01 eve).

D1: onset time answers («12 часов вечера», «вечером», hedged
«не знаю, где-то...») must ground as onset evidence — the probe must
never repeat verbatim, and the answer must not open a second episode.
D2: a repair re-ask must never be byte-identical to the just-spoken
question — clarify instead of echoing.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.issue_memory import extract_grounded_onset_value
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize(
    "answer",
    [
        "Я не знаю, где-то 12 часов вечера.",
        "Где-то 12 часов вечера.",
        "Вечером.",
        "12 часов вечера.",
    ],
)
def test_onset_time_grounds(answer: str) -> None:
    assert extract_grounded_onset_value(answer), answer


def test_onset_answer_advances_no_repeat_no_second_episode() -> None:
    r = ScenarioRunner(call_id="onset-live", elder_display_name="Тест")
    res = r.run(
        [
            CallStarted(),
            "Плохо.",
            "Беспокоит меня больше всего головная боль.",
            "Я не знаю, где-то 12 часов вечера.",
        ]
    )
    texts = [e.text for e in res.speak_effects]
    onsets = [t for t in texts if "началось" in t.lower() or "когда" in t.lower()]
    assert len(onsets) <= 1, onsets
    assert len(r.state.issue_episodes) == 1
    ep = next(iter(r.state.issue_episodes.values()))
    assert ep.known_attributes.get("onset"), ep.known_attributes


def test_bare_unknown_stays_unknown() -> None:
    assert extract_grounded_onset_value("Не знаю.") is None
    assert extract_grounded_onset_value("Не помню когда началось.") is None


def test_repair_never_echoes_identical_question() -> None:
    r = ScenarioRunner(call_id="repair-live", elder_display_name="Тест")
    res = r.run([CallStarted(), "Самое худшее.", "Алло, нормально себя чувствую."])
    texts = [e.text for e in res.speak_effects if e.text.strip()]
    for prev, cur in zip(texts, texts[1:]):
        assert prev.strip() != cur.strip(), (prev, cur)
