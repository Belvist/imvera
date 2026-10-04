"""A single accepted statement can settle multiple needs without another probe."""
import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn
from packages.dialogue_engine.semantic_kernel.types import SubjectKind

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture(autouse=True)
def pilot(monkeypatch):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")


@pytest.mark.parametrize("site,predicate", [("Голова", "болит"), ("Колено", "ноет")])
def test_volunteered_degree_settles_same_issue_with_its_own_source(site, predicate):
    text = f"{site} {predicate} со вчера, довольно сильно."
    result = interpret(text, utterance_id="u-multi")
    degrees = [o for o in result.observations if o.attribute == "severity"]
    assert len(degrees) == 1
    assert degrees[0].body_site == site.lower()
    assert degrees[0].subject == SubjectKind.SPEAKER
    assert degrees[0].evidence == "сильно" and degrees[0].source_turn_id == "u-multi"
    mentions = kernel_to_rich_turn(result).issue_mentions
    assert len(mentions) == 1 and mentions[0].severity == "сильно"
    runner = ScenarioRunner(call_id="multi-fact")
    out = runner.run([CallStarted(), text])
    ep = next(iter(runner.state.issue_episodes.values()))
    assert ep.known_attributes["severity"] == "сильно"
    assert "вчера" in ep.known_attributes["onset"]
    assert all("severity" not in speak.intent for speak in out.speak_effects)
    assert runner.state.pending_episode_attribute != "severity"


@pytest.mark.parametrize("text", [
    "Голова болела, но сейчас всё прошло.",
    "Колено ныло, но сейчас все прошло.",
    "Голова болела вчера, но сейчас всё прошло.",
])
def test_resolved_same_issue_is_not_reopened_for_clinical_questions(text):
    result = interpret(text, utterance_id="u-resolved")
    mentions = kernel_to_rich_turn(result).issue_mentions
    assert len(mentions) == 1 and mentions[0].status == "resolved"
    assert not mentions[0].onset or "сейчас" not in mentions[0].onset
    current = [o for o in result.observations if o.attribute == "current"]
    assert len(current) == 1 and current[0].temporal.current is False
    assert current[0].evidence == "прошло" and current[0].source_turn_id == "u-resolved"
    runner = ScenarioRunner(call_id="resolved-multi-fact")
    out = runner.run([CallStarted(), text])
    assert runner.state.pending_episode_attribute is None
    assert not any(speak.intent.startswith("episode_") for speak in out.speak_effects)
    assert all(ep.known_attributes.get("current") == "прошло"
               or ep.status == "resolved" for ep in runner.state.issue_episodes.values())


@pytest.mark.parametrize("text", [
    "Я потеряла ключи.", "Я потерял кошелёк.", "Я потеряла ключ от двери.",
    "Я потешалась над фильмом.", "Я потёрла стол.",
])
def test_spelling_prefix_does_not_turn_an_activity_into_a_symptom(text):
    result = interpret(text, utterance_id="u-world")
    assert not any(o.attribute == "issue" and o.subject == SubjectKind.SPEAKER
                   for o in result.observations)
    runner = ScenarioRunner(call_id="world-event")
    out = runner.run([CallStarted(), text])
    assert not runner.state.issue_episodes
    assert runner.state.pending_episode_attribute is None
    assert not any(speak.intent.startswith("episode_") for speak in out.speak_effects)


@pytest.mark.parametrize("text", [
    "Голова болит, дочь довольно сильная.",
    "Голова болит, я довольно сильно гуляла.",
    "У мужа голова болит, довольно сильно.",
    "Голова болит и живот ноет, довольно сильно.",
    "Голова болела, но сейчас все дела прошли хорошо.",
    "Голова болела, но сейчас у мужа прошло.",
    "Голова болела. Сейчас всё прошло.",
])
def test_degree_and_resolution_cannot_borrow_an_unrelated_antecedent(text):
    result = interpret(text, utterance_id="u-negative")
    assert not any(o.attribute in {"severity", "current"} and o.body_site == "голова"
                   and o.subject == SubjectKind.SPEAKER for o in result.observations)


@pytest.mark.parametrize("text,site,need", [
    ("Голова какая-то тяжёлая со вчера.", "голова", "current"),
    ("Ноги тяжёлые с утра.", "нога", None),
])
def test_nominal_sensation_gets_one_relevant_need_without_inventing_pain(text, site, need):
    runner = ScenarioRunner(call_id="sensation")
    out = runner.run([CallStarted(), text])
    assert len(runner.state.issue_episodes) == 1
    ep = next(iter(runner.state.issue_episodes.values()))
    assert ep.body_site == site and ep.subject == "speaker"
    assert runner.state.pending_episode_attribute == need
    assert "severity" not in ep.known_attributes
    assert "бол" not in out.speak_effects[-1].text.lower()
    if need is not None:
        assert out.speak_effects[-1].intent.endswith(need)
    else:
        assert not out.speak_effects[-1].intent.startswith("episode_")
    assert runner.state.current_thread_label != "рассказ"


@pytest.mark.parametrize("text", [
    "Голова куклы тяжёлая.", "У меня тяжёлый чемодан.",
    "С тяжёлой сумкой в руках иду домой.", "Голова тяжёлая у мужа.",
    "У дочери голова тяжёлая.", "В фильме голова тяжёлая.",
])
def test_sensation_adjective_does_not_create_a_speaker_symptom_without_its_owner(text):
    result = interpret(text, utterance_id="u-sensation-guard")
    assert not any(o.attribute == "issue" and o.subject == SubjectKind.SPEAKER
                   for o in result.observations)


@pytest.mark.parametrize("word,site", [("селезёнке", "селезенка"), ("ключице", "ключица")])
def test_exact_inflected_anatomy_survives_removal_of_spelling_guess(word, site):
    from packages.dialogue_engine.semantic_kernel.span_parser import _body_site_from_token

    assert _body_site_from_token(word) == site
