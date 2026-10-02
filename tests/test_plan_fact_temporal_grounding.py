"""Plans facts bind to the speaker's actual plan clause, not narrative keywords."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.issue_mention_extract import (
    extract_goal_facts,
    extract_issue_mentions,
)


def _plans(text: str, slot: str | None = None):
    return [fact for fact in extract_goal_facts(text, answer_slot=slot) if fact.field == "plans"]


@pytest.mark.parametrize("slot", [None, "plans"])
@pytest.mark.parametrize("text", [
    "Потом гуляли в саду.",
    "Вчера ходили в магазин.",
    "Я вчера была дома.",
    "Планировала погулять вчера.",
    "Сегодня гуляла в саду.",
])
def test_past_activity_never_becomes_current_plans(text, slot) -> None:
    assert _plans(text, slot) == []


@pytest.mark.parametrize("text", ["дома", "магазин", "ничего особенного", "сидеть дома"])
def test_pending_plans_preserves_elliptical_answers(text) -> None:
    facts = _plans(text, "plans")
    assert len(facts) == 1
    assert facts[0].value == text
    assert facts[0].evidence.quote == text


@pytest.mark.parametrize("text", ["магазин", "ничего особенного"])
def test_unasked_bare_topic_is_not_a_plan(text) -> None:
    assert _plans(text) == []


@pytest.mark.parametrize("text", [
    "Дома.",
    "Планов нет.",
    "Ничего не планирую.",
    "Завтра пойду в магазин.",
    "Планирую погулять.",
    "Сегодня дома.",
    "Сижу дома.",
    "Я пойду с внучкой в магазин.",
])
def test_volunteered_own_plans_remain_grounded(text) -> None:
    facts = _plans(text)
    assert len(facts) == 1
    fact = facts[0]
    assert fact.subject == "speaker"
    assert text[fact.evidence.start:fact.evidence.end] == fact.evidence.quote == fact.value


@pytest.mark.parametrize("slot", [None, "plans"])
@pytest.mark.parametrize("text", [
    "Внучка приезжала, потом гуляла в саду.",
    "Внучка завтра пойдёт в магазин.",
    "Я помню, муж завтра пойдёт в магазин.",
])
def test_other_person_activity_does_not_fill_speaker_plans(text, slot) -> None:
    assert _plans(text, slot) == []


@pytest.mark.parametrize("text, quote", [
    ("Вчера ходила в магазин, а завтра пойду гулять.", "завтра пойду гулять"),
    ("Вчера ходила в магазин и завтра пойду гулять.", "завтра пойду гулять"),
    ("Внучка приезжала, а я завтра пойду в магазин.", "я завтра пойду в магазин"),
    ("Внучка приезжала, а завтра пойду в магазин.", "завтра пойду в магазин"),
    ("Я пойду в магазин, а дочь вчера гуляла.", "Я пойду в магазин"),
    ("Вчера ходила в магазин завтра пойду гулять.", "завтра пойду гулять"),
    ("Спина болит сегодня пойду в магазин.", "сегодня пойду в магазин"),
])
def test_mixed_turn_grounds_only_own_future_clause(text, quote) -> None:
    facts = _plans(text)
    assert len(facts) == 1
    assert facts[0].value == quote
    assert facts[0].evidence.quote == quote
    assert text[facts[0].evidence.start:facts[0].evidence.end] == quote


def test_plan_scope_does_not_remove_health_evidence() -> None:
    text = "Спина болит с вчера, а завтра пойду в магазин."
    mentions = extract_issue_mentions(text)
    assert any(mention.body_site == "спина" for mention in mentions)
    plans = _plans(text)
    assert len(plans) == 1
    assert plans[0].value == plans[0].evidence.quote == "завтра пойду в магазин"


@pytest.mark.parametrize("text", ["Дома буду.", "Планов нет.", "Завтра пойду в магазин!"])
def test_single_plan_turn_preserves_exact_original_source(text) -> None:
    fact, = _plans(text)
    assert fact.value == fact.evidence.quote == text
    assert (fact.evidence.start, fact.evidence.end) == (0, len(text))


@pytest.mark.parametrize("text, quote", [
    ("Планов никаких.", "Планов никаких."),
    ("Никаких планов.", "Никаких планов."),
    ("Плохо сегодня, почти не спал, планов никаких.", "планов никаких"),
])
def test_explicit_absence_of_plans_survives_without_a_verb(text, quote) -> None:
    fact, = _plans(text)
    assert fact.value == fact.evidence.quote == quote
    assert text[fact.evidence.start:fact.evidence.end] == quote


@pytest.mark.parametrize("text", ["Вчера гуляли, дома.", "Внучка дома."])
def test_home_inside_history_or_other_person_report_is_not_own_activity(text) -> None:
    assert _plans(text) == []
