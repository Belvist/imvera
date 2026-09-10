"""System invariants after live-path simplification — no phrase-specific patches."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


def _runner(cid: str = "sys") -> ScenarioRunner:
    return ScenarioRunner(call_id=cid, elder_display_name="Даниил")


def _intents(r: ScenarioRunner) -> list[str]:
    return [e.intent for e in r.effects if hasattr(e, "intent")]


@pytest.mark.parametrize(
    "concern",
    [
        "Третий день горло болит.",
        "С утра шею тянет.",
        "Вчера ухо заложило.",
        "Со вчера головная боль.",
    ],
)
def test_pending_concern_issue_survives(concern: str) -> None:
    r = _runner(f"concern-{hash(concern) % 10000}")
    r.run([CallStarted(), "Вроде нормально, но чувствую себя плохо.", concern])
    assert r.state.issue_episodes, f"issue lost for {concern!r}"
    # Must follow the issue before hanging up on ITS/summary alone.
    assert any(
        i.startswith("episode_") or i.startswith("probe_") or i.startswith("topic_")
        for i in _intents(r)
    ), _intents(r)


def test_vague_wellness_asks_concern_not_duration() -> None:
    r = _runner("vague")
    r.run([CallStarted(), "Вроде нормально, но чувствую себя плохо."])
    intents = _intents(r)
    assert "probe_concern" in intents
    assert "probe_duration" not in intents


def test_its_meta_does_not_close() -> None:
    r = _runner("its-meta")
    r.run([CallStarted(), "Хорошо.", "А вы больше ничего не хотите спросить?"])
    intents = _intents(r)
    assert "summary" not in intents
    assert r.state.observations.get("important_to_share") in (None, "")
    assert r.state.call_closed is False


@pytest.mark.parametrize(
    "meta",
    ["И это всё?", "Вы меня вообще слушаете?", "Не спросишь там, ещё что-то."],
)
def test_its_meta_variants_stay_open(meta: str) -> None:
    r = _runner(f"meta-{hash(meta) % 10000}")
    r.run([CallStarted(), "Хорошо.", meta])
    assert "summary" not in _intents(r)
    assert r.state.call_closed is False


def test_its_true_new_issue_returns_to_episode() -> None:
    r = _runner("its-issue")
    r.run([CallStarted(), "Хорошо.", "Ещё колено второй день болит."])
    assert r.state.issue_episodes
    intents = _intents(r)
    assert "summary" not in intents or any(i.startswith("episode_") for i in intents)
    assert "Хорошо, записала" not in " ".join(
        e.text for e in r.effects if hasattr(e, "text")
    )


@pytest.mark.parametrize("bye", ["До свидания.", "Пока.", "Всего доброго."])
def test_explicit_farewell_no_confirm(bye: str) -> None:
    r = _runner(f"bye-{hash(bye) % 10000}")
    r.run([CallStarted(), "Хорошо.", "Нет.", bye])
    intents = _intents(r)
    assert "goodbye_final" in intents or r.state.call_closed
    assert "goodbye_confirm" not in intents


def test_ambiguous_end_hint_may_confirm() -> None:
    r = _runner("ambig")
    r.run([CallStarted(), "Хорошо.", "Нет."])
    # After summary, ambiguous «всё» alone may confirm — not required if already closed.
    from packages.dialogue_engine.events import User

    before = len(r.effects)
    r._apply(User(text="Ну всё."))
    intents = [e.intent for e in r.effects[before:] if hasattr(e, "intent")]
    assert intents  # never silent


# Full conversation fuzz — body sites / wording shuffled; protect system invariants.
_VAGUE = (
    "Вроде нормально, но чувствую себя плохо.",
    "Вроде хорошо, но состояние плохое.",
    "Неплохо, но что-то не так.",
)
_ISSUES = (
    "Со вчера головная боль.",
    "Третий день горло болит.",
    "С утра шею тянет.",
    "Вчера ухо заложило.",
    "Живот немного побаливает.",
    "Зуб ночью начал болеть.",
    "Колено второй день ноет.",
    "Спина с утра ломит.",
)
_FOLLOWUPS = (
    "Со вчерашнего дня.",
    "Терпимо.",
    "Сейчас ещё есть.",
)
_META = (
    "А вы больше ничего не хотите спросить?",
    "И это всё?",
    "Вы меня вообще слушаете?",
)
_NEW_AT_ITS = (
    "Ещё колено второй день болит.",
    "И ещё горло першит.",
    "Плюс зуб ноет.",
)
_BYES = ("До свидания.", "Пока.", "Всего доброго.")


@pytest.mark.parametrize("vague", _VAGUE)
@pytest.mark.parametrize("issue", _ISSUES)
def test_fuzz_vague_then_issue_not_lost(vague: str, issue: str) -> None:
    r = _runner(f"fuzz-{hash((vague, issue)) % 100000}")
    r.run([CallStarted(), vague, issue])
    assert r.state.issue_episodes, f"lost issue for {vague!r} + {issue!r}"
    assert "summary" not in _intents(r) or any(
        i.startswith("episode_") for i in _intents(r)
    )


@pytest.mark.parametrize("meta", _META)
@pytest.mark.parametrize("bye", _BYES)
def test_fuzz_its_meta_then_farewell(meta: str, bye: str) -> None:
    r = _runner(f"fuzz-meta-{hash((meta, bye)) % 100000}")
    r.run([CallStarted(), "Хорошо.", meta, bye])
    intents = _intents(r)
    assert "goodbye_confirm" not in intents
    # Meta must not close the call by itself before farewell.
    assert r.state.call_closed or "goodbye_final" in intents


@pytest.mark.parametrize("new_issue", _NEW_AT_ITS)
def test_fuzz_new_issue_at_its(new_issue: str) -> None:
    r = _runner(f"fuzz-its-{hash(new_issue) % 100000}")
    r.run([CallStarted(), "Хорошо.", new_issue])
    assert r.state.issue_episodes
    spoken = " ".join(e.text for e in r.effects if hasattr(e, "text"))
    assert "Хорошо, записала" not in spoken


@pytest.mark.parametrize("follow", _FOLLOWUPS)
def test_fuzz_followup_after_issue(follow: str) -> None:
    r = _runner(f"fuzz-fu-{hash(follow) % 100000}")
    r.run([CallStarted(), "Вроде плохо.", "Голова болит.", follow])
    assert r.state.issue_episodes
    # Meaningful follow-up must not vanish into silence.
    assert _intents(r)
