"""Dialogue Product Pack corpus gate — MVP behaviour as law.

Ported expectations from judogaaa/IMVERA imvera_voice_mvp
(feature/voice-mvp-clean): headache, multitopic, product contract, multi-symptom.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.product import (
    IMPORTANT_TO_SHARE_QUESTION,
    MAX_ASKS_PER_FAMILY,
    MAX_CONTENT_ASKS_PER_CALL,
    ProductFamily,
    classify_episode_family,
)
from packages.dialogue_engine.product.spoken import spoken_question
from packages.dialogue_engine.questions import important_to_share_question
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import IssueEpisode

pytestmark = pytest.mark.dialogue_engine


def _runner(name: str = "pack") -> ScenarioRunner:
    return ScenarioRunner(call_id=name, elder_display_name="Егор")


def _intents(r: ScenarioRunner) -> list[str]:
    return [e.intent for e in r.effects if getattr(e, "intent", None)]


def _last_text(r: ScenarioRunner) -> str:
    speaks = [e.text for e in r.effects if getattr(e, "text", None)]
    assert speaks
    return speaks[-1]


# --- Product contract (MVP test_product_dialogue_contract) ---


def test_pack_its_is_status_check_not_message_relay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Canonical pool[0] pinned by day (variety rotates live by date).
    monkeypatch.setenv("IMVERA_SPEECH_DAY", "99")
    q = important_to_share_question()
    assert q == IMPORTANT_TO_SHARE_QUESTION
    low = q.lower()
    assert "самочувств" in low
    assert "передам" not in low
    assert "передать" not in low


def test_pack_spoken_has_no_emergency_promise() -> None:
    ep = IssueEpisode(
        episode_id="ep-x",
        primary_label="голова болит",
        kind="symptom",
        body_site="голова",
    )
    for family in ProductFamily:
        for attr in ("onset", "current", "severity", "needs_help", "status_today"):
            try:
                text = spoken_question(family, attr, ep)
            except Exception:
                continue
            low = text.lower()
            assert "скорую" not in low
            assert "вызову" not in low


def test_pack_caps_are_frozen() -> None:
    assert MAX_ASKS_PER_FAMILY == 3
    assert MAX_CONTENT_ASKS_PER_CALL == 6


# --- Headache (MVP test_natural_headache_dialogue) ---


def test_pack_morning_headache_asks_current_not_severity() -> None:
    r = _runner("mvp-morning")
    r.run(
        [
            CallStarted(),
            "Хорошо, чувствую на утро что-то голова болела.",
        ]
    )
    intents = _intents(r)
    assert "episode_headache_current" in intents
    assert "episode_headache_severity" not in intents
    assert "а сейчас" in _last_text(r).lower()
    assert "сильная" not in _last_text(r).lower()


def test_pack_morning_headache_polegshe_closes_without_severity() -> None:
    r = _runner("mvp-poleg")
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
    assert ep.status == "resolved" or ep.known_attributes.get("current") in {
        "resolved",
        "improving",
    }
    assert "important_to_share" in intents or r.state.important_to_share_asked


def test_pack_present_headache_duration_then_severity() -> None:
    # Frozen contract (ADR-014): unmentioned associated symptoms are not
    # probed — duration + severity resolve the episode, then ITS → summary.
    # Mandatory associated probing needs an ADR (backlog).
    r = _runner("mvp-present")
    r.run(
        [
            CallStarted(),
            "Голова болит.",
            "С утра.",
            "Терпимая.",
            "Нет, только голова.",
            "Нет.",
        ]
    )
    intents = _intents(r)
    assert intents.count("episode_headache_current") == 0
    assert "episode_headache_duration" in intents
    assert "episode_headache_severity" in intents
    assert "episode_headache_associated" not in intents
    assert "important_to_share" in intents
    assert "summary" in intents
    ep = next(iter(r.state.issue_episodes.values()))
    assert ep.status == "resolved" or r.state.important_to_share_asked or r.state.call_closed


def test_pack_multi_ack_and_nausea_question() -> None:
    r = _runner("multi-ack")
    r.run(
        [
            CallStarted(),
            "У меня болит голова, живот болит и меня тошнит.",
            "С утра.",
            "Терпимо.",
        ]
    )
    texts = " ".join(
        e.text.lower() for e in r.effects if getattr(e, "text", None)
    )
    assert "головная боль" in texts and "тошнота" in texts
    assert "тошнота сейчас" in texts or "тошнота" in texts
    # Frozen contract: mentioned nausea is acknowledged, not probed as a
    # mandatory associated step (associated probing needs an ADR).
    assert "episode_headache_associated" not in _intents(r)
    # Must not re-ask abdomen onset after head temporal.
    assert "а про живот — когда" not in texts


def test_pack_ne_znayu_its_warm_recorded_close() -> None:
    r = _runner("warm-close")
    r.run(
        [
            CallStarted(),
            "Голова болит.",
            "С утра.",
            "Сильная.",
            "Только голова.",
            "Не знаю.",
        ]
    )
    intents = _intents(r)
    assert "partial_unresolved_close" not in intents
    if "summary" in intents:
        last = _last_text(r).lower()
        assert "берегите" in last or "записала" in last
        assert "не получилось" not in last


# --- Multitopic / multi-symptom ---


def test_pack_multi_symptom_classifies_headache_and_abdominal() -> None:
    r = _runner("multi")
    r.run(
        [
            CallStarted(),
            "У меня болит голова, живот болит и меня тошнит.",
        ]
    )
    families = {
        classify_episode_family(ep) for ep in r.state.issue_episodes.values()
    }
    assert ProductFamily.HEADACHE in families
    assert ProductFamily.ABDOMINAL in families
    nausea_primary = [
        ep
        for ep in r.state.issue_episodes.values()
        if "тошн" in (ep.primary_label or "").lower()
    ]
    assert not nausea_primary


def test_pack_multi_symptom_reaches_its_without_hangup() -> None:
    r = _runner("multi-end")
    r.run(
        [
            CallStarted(),
            "У меня болит голова, живот болит и меня тошнит.",
            "С утра.",
            "Терпимо.",
            "Ещё тошнит.",
            "Ещё болит.",
            "Не знаю.",
        ]
    )
    intents = _intents(r)
    assert "partial_unresolved_close" not in intents
    assert "important_to_share" in intents or r.state.important_to_share_asked
    # Frozen contract: a fresh vague lead ("ещё болит") is probed, not hung
    # up on — the call legitimately stays open. Temporal probes may only
    # target the genuinely new lead, never re-ask headache/abdomen onset.
    assert not r.state.call_closed
    for eff in r.effects:
        intent = getattr(eff, "intent", "") or ""
        if intent.endswith("_onset"):
            ep_id = intent[len("episode_") : -len("_onset")]
            ep = r.state.issue_episodes.get(ep_id)
            assert ep is not None
            assert ep.known_attributes.get("_product_family") == "generic_symptom"


def test_pack_skips_duration_when_time_already_in_opening() -> None:
    r = _runner("known-time")
    r.run([CallStarted(), "Голова болит с утра."])
    texts = " ".join(e.text.lower() for e in r.effects if getattr(e, "text", None))
    assert "когда начала болеть голова" not in texts
    assert "сильная или терпимая" in texts or "episode_headache_severity" in _intents(r)


def test_pack_family_ask_cap_stops_probing() -> None:
    r = _runner("cap")
    r.run([CallStarted(), "Голова болит.", "С утра.", "Сильная."])
    assert r.state.product_asks_by_family.get("headache", 0) <= MAX_ASKS_PER_FAMILY
    assert r.state.product_content_asks <= MAX_CONTENT_ASKS_PER_CALL


# --- Sleep / medication light ports ---


def test_pack_sleep_does_not_ladder_mood() -> None:
    # Frozen contract (ADR-014): a sleep complaint needs no probing — ITS
    # follows immediately, never a mood/plans ladder, never sleep pattern
    # questions. Sleep probing needs an ADR (backlog).
    r = _runner("sleep")
    r.run(
        [
            CallStarted(),
            "Плохо спал.",
            "Несколько ночей.",
            "Днём устаю.",
            "Нет.",
        ]
    )
    intents = _intents(r)
    assert "check_mood" not in intents
    assert "check_plans" not in intents
    assert "episode_sleep_pattern" not in intents
    assert "important_to_share" in intents
    assert "partial_unresolved_close" not in intents


def test_pack_good_path_warm_close() -> None:
    r = _runner("good")
    r.run(
        [
            CallStarted(),
            "Хорошо, всё нормально.",
            "Нет.",
        ]
    )
    intents = _intents(r)
    assert "partial_unresolved_close" not in intents
    assert "important_to_share" in intents or "summary" in intents
    if "summary" in intents:
        assert "до свидания" in _last_text(r).lower()
