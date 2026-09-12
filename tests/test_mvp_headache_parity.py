"""MVP behavioural parity — headache morning path (imvera_voice_mvp).

Source: judogaaa/IMVERA feature/voice-mvp-clean imvera_voice_mvp
tests/test_natural_headache_dialogue.py — ported to ScenarioRunner.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="mvp-headache", elder_display_name="Егор")


def _intents(r: ScenarioRunner) -> list[str]:
    return [e.intent for e in r.effects if hasattr(e, "intent")]


def _last_speak(r: ScenarioRunner) -> str:
    speaks = [e for e in r.effects if getattr(e, "text", None)]
    assert speaks, "expected Vera speech"
    return speaks[-1].text.lower()


def test_mvp_morning_headache_asks_current_not_severity() -> None:
    """«…на утро голова болела» → trend/current («а сейчас»), not severity."""
    r = _runner()
    r.run(
        [
            CallStarted(),
            "Хорошо, чувствую на утро что-то голова болела.",
        ]
    )
    intents = _intents(r)
    assert "episode_headache_current" in intents
    assert "episode_headache_severity" not in intents
    reply = _last_speak(r)
    assert "а сейчас" in reply
    assert "сильная" not in reply


def test_mvp_morning_headache_polegshe_closes_without_reask() -> None:
    """«Сейчас уже полегче» must resolve — no severity re-ask / no associated loop."""
    r = _runner()
    r.run(
        [
            CallStarted(),
            "Хорошо, чувствую на утро что-то голова болела.",
            "Сейчас уже полегче.",
        ]
    )
    intents = _intents(r)
    assert "episode_headache_severity" not in intents
    ep = next(iter(r.state.issue_episodes.values()))
    assert ep.status == "resolved" or ep.known_attributes.get("current") == "resolved"
    assert "important_to_share" in intents or r.state.important_to_share_asked


def test_mvp_improved_skips_severity_after_active_pain() -> None:
    """Bare «голова болит» → current; «уже полегче» closes without severity."""
    r = _runner()
    r.run([CallStarted(), "Голова болит.", "С утра, сейчас уже полегче."])
    intents = _intents(r)
    assert "episode_headache_severity" not in intents
    ep = next(iter(r.state.issue_episodes.values()))
    assert ep.status == "resolved" or ep.known_attributes.get("current") == "resolved"
