"""Accepted reports receive a reaction on every ordinary SDK exit path."""

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.response_plan import ResponsePlan, compose_speech
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import EngineState

pytestmark = pytest.mark.dialogue_engine


def started(*steps):
    runner = ScenarioRunner(call_id="responsive-dialogue", elder_display_name="Тамара Юрьевна")
    runner.run([CallStarted(), *steps])
    return runner


def speech(result):
    return " ".join(effect.text for effect in result.speak_effects)


@pytest.mark.parametrize("report,site,word", [
    ("Руки болят уже две недели.", "рука", "руки болят"),
    ("Голова болит уже две недели, но терпимо.", "голова", "голова болит"),
    ("Живот болит уже две недели, но терпимо.", "живот", "живот болит"),
])
def test_full_answer_gets_a_grounded_reaction_without_a_new_interview(report, site, word):
    runner = started()
    result = runner.run([report])
    text = speech(result).lower()
    assert word in text and "жаль" in text
    assert text.count("?") == 1
    assert "давайте по порядку" not in text
    assert result.speak_effects[-1].intent == "important_to_share"
    ep = next(ep for ep in runner.state.issue_episodes.values() if ep.body_site == site)
    assert "две недели" in str(ep.known_attributes)
    assert ep.known_attributes.get("current") == "active"
    assert runner.state.pending_episode_attribute is None
    assert runner.state.delivered_question.slot == "important_to_share"


def test_complete_multi_report_does_not_announce_questions_it_will_not_ask():
    runner = started()
    result = runner.run(["Голова болит с утра терпимо, руки ноют сейчас."])
    text = speech(result).lower()
    assert "голова болит и руки ноют" in text
    assert "давайте по порядку" not in text
    assert text.count("?") == 1
    assert runner.state.pending_episode_attribute is None
    assert len(runner.state.issue_episodes) == 2
    head = next(ep for ep in runner.state.issue_episodes.values() if ep.body_site == "голова")
    assert head.known_attributes.get("severity") == "терпимо"


def test_report_before_summary_is_heard_without_adding_a_question():
    runner = started("Руки болят уже две недели.")
    result = runner.run(["Руки трясутся со вчера сильно."])
    text = speech(result).lower()
    assert "слышу" in text and "руки трясутся" in text
    assert "давайте уточним" not in text and "давайте по порядку" not in text
    assert text.count("?") == 0
    effect = result.speak_effects[-1]
    assert effect.intent == "summary"
    assert effect.text == " ".join(
        part for part in (effect.bridge_text, effect.question_text) if part
    )
    assert not effect.marks_question
    assert runner.state.summary_delivered
    assert len(runner.state.issue_episodes) == 2
    tremor = next(ep for ep in runner.state.issue_episodes.values() if "тряс" in ep.primary_label)
    assert tremor.known_attributes.get("severity") == "сильно"
    assert "головная боль" not in text
    assert "сильная боль" not in text


def test_strong_answer_handoff_names_the_next_topic():
    runner = started("Голова болит и руки ноют.", "Сегодня.")
    result = runner.run(["Сильно."])
    text = speech(result).lower()
    assert "сильная боль — это тяжело" in text and "теперь про руки" in text
    assert text.count("?") == 1
    assert runner.state.issue_episodes[runner.state.active_episode_id].body_site == "рука"
    assert runner.state.pending_episode_attribute == "onset"
    head = next(ep for ep in runner.state.issue_episodes.values() if ep.body_site == "голова")
    hands = runner.state.issue_episodes[runner.state.active_episode_id]
    assert head.known_attributes["severity"] == "Сильно."
    assert not hands.known_attributes.get("severity")


@pytest.mark.parametrize("report,expected", [
    ("Голова кружится и живот болит.", "голова кружится"),
    ("Голова немеет и живот болит.", "голова немеет"),
    ("Голова кружится и тошнит.", "голова кружится"),
])
def test_anatomy_never_invents_pain_in_a_multi_report(report, expected):
    runner = started()
    result = runner.run([report])
    text = speech(result).lower()
    assert expected in text
    assert "головная боль" not in text and "голова болит" not in text
    assert text.count("?") == 1
    labels = [ep.primary_label for ep in runner.state.issue_episodes.values()]
    assert not any("головная боль" in label for label in labels)


@pytest.mark.parametrize("answer", ["Терпимо", "Терпимо.", "Терпимо!", "Терпимо…"])
def test_acknowledgment_accepts_quote_punctuation_without_changing_its_value(answer):
    runner = started("Голова болит.", "Не помню.")
    ep_id = runner.state.active_episode_id
    result = runner.run([answer])
    assert "сейчас терпимо" in speech(result).lower()
    assert runner.state.issue_episodes[ep_id].known_attributes["severity"].lower().rstrip(
        ".!?…"
    ) == "терпимо"
    assert not runner.state.issue_episodes[ep_id].known_attributes.get("duration")
    assert runner.state.pending_episode_attribute is None


@pytest.mark.parametrize("answer", ["Уже не болит.", "Сейчас уже лучше."])
def test_relief_reacts_only_to_the_accepted_current_observation(answer):
    runner = started("Голова болит.")
    ep_id = runner.state.active_episode_id
    result = runner.run([answer])
    assert "рада, что сейчас вам легче" in speech(result).lower()
    assert runner.state.issue_episodes[ep_id].known_attributes["current"] == "resolved"
    assert runner.state.pending_episode_attribute is None
    assert "выздоровели" not in speech(result).lower()


@pytest.mark.parametrize("answer", [
    "Давайте лучше про работу.", "У мужа голова уже не болит.",
    "Не помню.", "Голова болела вчера.",
])
def test_no_relief_claim_from_topic_choice_other_person_unknown_or_past(answer):
    runner = started("Голова болит.")
    result = runner.run([answer])
    assert "рада, что сейчас вам легче" not in speech(result).lower()


@pytest.mark.parametrize("story", [
    "Мне одиноко, скучаю по дочери.",
    "Внучка приезжала, хорошо посидели.",
])
def test_personal_thread_invites_a_story_and_consumes_its_hook_once(story):
    runner = started()
    result = runner.run([story])
    text = speech(result).lower()
    assert "хотите рассказать" in text
    assert "самое главное" not in text
    assert runner.state.open_hook.lower().rstrip(".!?…") in text
    assert runner.state.open_hook_used
    assert text.count("?") == 1
    assert result.speak_effects[-1].intent == "thread_followup"
    again = runner.run(["Нет."])
    assert "хотите рассказать" not in speech(again).lower()


@pytest.mark.parametrize("kind,value,phrase", [
    ("temporal_answer", "две недели", "продолжается уже две недели"),
    ("tolerable_answer", "", "сейчас терпимо"),
    ("strong_answer", "", "сильную боль тяжело переносить"),
])
def test_summary_renderer_uses_the_ack_once_and_is_read_only(kind, value, phrase):
    state = EngineState(call_id="summary-compose", elder_display_name="Тамара")
    before = state.model_dump()
    plan = ResponsePlan(
        action="close_summary", acknowledgement_kind=kind, acknowledgement_value=value,
    )
    first = compose_speech(plan, state)
    assert first.lower().count(phrase) == 1
    assert "?" not in first and plan.intent == "summary" and not plan.marks_question
    assert compose_speech(plan, state) == first
    assert state.model_dump() == before


def test_summary_with_explicit_ack_does_not_duplicate_it():
    state = EngineState(call_id="ack-summary")
    plan = ResponsePlan(action="close_summary", acknowledge="Спасибо, что рассказали.")
    text = compose_speech(plan, state)
    assert text.count("Спасибо") == 1
    assert text.count("На сегодня всё") == 1
    assert compose_speech(plan, state) == text


@pytest.mark.parametrize("report", [
    "Не хочу разговаривать, голова болит.",
    "До свидания, руки трясутся.",
    "Не могу дышать, руки болят.",
])
def test_control_and_urgent_paths_do_not_get_an_ordinary_report_reaction(report):
    runner = started()
    result = runner.run([report])
    text = speech(result).lower()
    assert runner.state.call_closed
    assert "?" not in text
    assert "жаль, что" not in text and "давайте по порядку" not in text
    assert len(result.speak_effects) == 1
