"""Subject preservation end-to-end (reviewer item 2).

Acceptance: a husband's complaint is NEVER recorded as the speaker's
wellness, NEVER triggers a question about the speaker's own pain, and
corrections («нет, я про мужа») reassign instead of re-asking.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner


@pytest.fixture(autouse=True)
def _pilot_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")


def run(turns: list) -> tuple[ScenarioRunner, list[str]]:
    r = ScenarioRunner(call_id="subj", elder_display_name="Тест")
    intents: list[str] = []
    for t in turns:
        res = r.run([t])
        for e in res.speak_effects:
            assert isinstance(e, SpeakEffect)
            intents.append(e.intent)
    return r, intents


def test_husband_complaint_not_speaker_wellness() -> None:
    r, intents = run([CallStarted(), "У мужа голова болит."])
    from packages.contracts.enums import SlotStatus

    assert r.state.slots.get("wellness") == SlotStatus.OPEN
    assert all(
        e.subject != "speaker" for e in r.state.issue_episodes.values()
    )
    # No question about the speaker's OWN head pain.
    assert "episode_headache_duration" not in intents
    assert "episode_headache_severity" not in intents


def test_mixed_turn_splits_subjects() -> None:
    r, _ = run([CallStarted(), "У мужа голова, а у меня живот болит."])
    labels = {e.primary_label: e.subject for e in r.state.issue_episodes.values()}
    assert labels.get("живот болит") == "speaker"
    assert "голова" not in " ".join(
        e.primary_label for e in r.state.issue_episodes.values() if e.subject == "speaker"
    )


def test_correction_reassigns_and_stops_probing() -> None:
    r, intents = run(
        [CallStarted(), "Голова болит.", "С утра.", "Нет, я про мужа."]
    )
    ep = next(iter(r.state.issue_episodes.values()))
    assert ep.subject == "other_person"
    # No further speaker-directed severity probe after the correction.
    tail = intents[intents.index("episode_headache_severity") + 1 :]
    assert "episode_headache_severity" not in tail


def test_other_person_absent_from_summary() -> None:
    from packages.dialogue_engine.questions import concern_summary_phrase

    r, _ = run([CallStarted(), "У мужа голова болит.", "Я нормально."])
    phrase = concern_summary_phrase(r.state)
    assert "голов" not in phrase.lower()
