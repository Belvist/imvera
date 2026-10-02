"""Clinical degree continuations keep their sole grounded symptom and onset."""

import pytest

from packages.dialogue_engine.events import CallStarted, UserTurnReceived
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn
from packages.dialogue_engine.semantic_kernel.types import SubjectKind
from packages.dialogue_engine.state import EngineState

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize("text,site,degree", [
    ("Голова болит со вчера, сейчас сильная боль", "голова", "сильная"),
    ("Голова болит со вчера, сейчас боль сильная", "голова", "сильная"),
    ("Голова болит со вчера, сейчас сильно", "голова", "сильно"),
    ("Голова болела вчера, сейчас сильная боль", "голова", "сильная"),
    ("Колено ноет с утра, сейчас сильная боль", "колено", "сильная"),
    ("Голова болит со вчера, но сейчас терпимо", "голова", "терпимо"),
])
def test_current_degree_continuation_keeps_one_symptom_and_original_onset(text, site, degree):
    result = interpret(text, utterance_id="u-clinical")
    mentions = kernel_to_rich_turn(result).issue_mentions
    assert len(mentions) == 1
    mention = mentions[0]
    assert mention.body_site == site
    assert mention.status == "active"
    assert mention.severity == degree
    assert mention.onset and "сейчас" not in mention.onset
    severity = [o for o in result.observations if o.attribute == "severity"]
    assert len(severity) == 1
    assert severity[0].body_site == site and severity[0].evidence == degree
    assert severity[0].subject == SubjectKind.SPEAKER
    assert any(o.attribute == "current" and o.temporal.current is True
               and o.evidence == "сейчас" for o in result.observations)


@pytest.mark.parametrize("text", [
    "Голова болит, боль сильная",
    "Голова болит, сильная боль",
    "Колено ноет, боль терпимая",
])
def test_nominal_pain_without_repeated_anatomy_keeps_its_owner(text):
    result = interpret(text, utterance_id="u-nominal")
    mentions = kernel_to_rich_turn(result).issue_mentions
    assert len(mentions) == 1
    assert mentions[0].body_site and mentions[0].severity
    assert not any(o.attribute == "current" for o in result.observations)


@pytest.mark.parametrize("text", [
    "Голова болит и живот ноет, сейчас сильная боль",
    "Голова болит, живот ноет, сейчас сильно",
    "Голова болит, руки трясутся, сейчас сильная боль",
    "Голова болит, сейчас фильм сильный",
    "Голова болит, сейчас сильная дочь",
    "Голова болит, сейчас сильно гуляла",
    "Голова болит и гуляла, сейчас сильная боль",
    "Голова болит, погуляла, сейчас сильная боль",
    "Голова болит, сейчас сильно не болит",
    "Голова болит, боль не сильная",
    "Голова болит, сейчас наверное сильная боль",
    "Голова не болит, сейчас сильная боль",
    "Голова болит. Сейчас сильная боль",
    "Голова болит, сейчас у мужа сильная боль",
    "Голова болит, у меня сильная боль в животе",
    "У мужа голова болит, сейчас сильная боль",
    "У коллеги голова болит, сейчас сильная боль",
])
def test_ambiguous_or_different_predicate_never_attaches_degree_to_head(text):
    result = interpret(text, utterance_id="u-guard")
    assert not any(o.attribute == "severity" and o.body_site == "голова"
                   and o.subject == SubjectKind.SPEAKER for o in result.observations)


def test_sdk_reducer_records_volunteered_onset_current_and_degree_without_unsited_episode():
    state, _ = reduce(EngineState(call_id="clinical-ellipsis"), CallStarted())
    text = "Голова болит со вчера, сейчас сильная боль"
    parsed = interpret(text, utterance_id="u-clinical", engine_state=state)
    rich = kernel_to_rich_turn(parsed, engine_state=state)
    state, _ = reduce(state, UserTurnReceived(
        turn_id="u-clinical", utterance_id="u-clinical", text=text, rich_turn=rich,
    ))
    episodes = [e for e in state.issue_episodes.values() if e.subject == "speaker"]
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.body_site == "голова"
    # Existing episode status also denotes administrative completion. Clinical
    # resolution must be judged from the grounded current value/mention.
    from packages.dialogue_engine.question_context import current_value_indicates_resolved

    assert not current_value_indicates_resolved(episode.known_attributes["current"])
    assert all(m.status == "active" for m in episode.mentions)
    assert episode.known_attributes["severity"] == "сильная"
    assert "вчера" in episode.known_attributes["onset"]
    assert episode.known_attributes["current"] == "сейчас"


@pytest.mark.parametrize("text", [
    "Голова болит со вчера", "Голова болит утром", "Колено ноет со вчера",
    "Живот болит со вчера", "Руки болят со вчера", "Голова болит позавчера и сегодня",
])
def test_present_symptom_with_old_onset_is_not_improvement(text):
    result = interpret(text, utterance_id="u-present")
    issues = [o for o in result.observations if o.attribute == "issue"]
    assert issues and all(o.temporal.current is True for o in issues)
    mentions = kernel_to_rich_turn(result).issue_mentions
    assert mentions and all(m.status == "active" for m in mentions)
    assert all(m.onset for m in mentions)


@pytest.mark.parametrize("text", [
    "Голова болела вчера", "Колено ныло вчера", "Вчера боль в голове",
    "Утром голова болела",
])
def test_past_symptom_does_not_prove_improvement_or_current_activity(text):
    result = interpret(text, utterance_id="u-past")
    issues = [o for o in result.observations if o.attribute == "issue"]
    assert issues and all(o.temporal.current is None for o in issues)
    mentions = kernel_to_rich_turn(result).issue_mentions
    assert mentions and all(m.status == "unknown" for m in mentions)
    assert not any(o.attribute == "current" for o in result.observations)


@pytest.mark.parametrize("text", ["Голова не болит со вчера", "Голова болела вчера, сейчас прошло"])
def test_explicit_negation_or_resolution_still_wins_over_tense(text):
    result = interpret(text, utterance_id="u-resolved")
    assert not any(o.attribute == "issue" and o.temporal.current is True
                   for o in result.observations)


@pytest.mark.parametrize("text", ["Голова болела вчера, сейчас прошло"])
def test_grounded_resolved_continuation_keeps_its_own_evidence(text):
    result = interpret(text, utterance_id="u-resolved-clause")
    mentions = kernel_to_rich_turn(result).issue_mentions
    assert len(mentions) == 1 and mentions[0].status == "resolved"
    assert any(o.attribute == "current" and o.temporal.current is False
               and o.evidence == "прошло" for o in result.observations)
    assert not any(o.attribute == "current" and o.temporal.current is True
                   for o in result.observations)


def test_explicit_past_resolved_frame_keeps_existing_suppression():
    text = "Голова болела утром, но уже прошло"
    result = interpret(text, utterance_id="u-past-resolved")
    assert result.observations == ()
    assert kernel_to_rich_turn(result).issue_mentions == ()


@pytest.mark.parametrize("text", [
    "Голова болела вчера и гуляла, сейчас нормально",
    "Голова болела вчера, дочь сейчас нормально",
    "Голова болела и живот болел вчера, сейчас прошло",
])
def test_unowned_status_cannot_prove_headache_resolved(text):
    result = interpret(text, utterance_id="u-unowned-status")
    assert not any(o.attribute == "current" and o.body_site == "голова"
                   and o.temporal.current is False for o in result.observations)


@pytest.mark.parametrize("story", [
    "Вчера с дочерью чай пили", "Вчера с сыном гуляли", "Вчера с мужем обедали",
])
@pytest.mark.parametrize("boundary", [", а ", " а ", " А ", "   а   "])
def test_canonical_sdk_keeps_symptom_inside_story_and_delivers_no_redundant_probe(story, boundary):
    from packages.dialogue_engine.scenario_runner import ScenarioRunner
    from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

    runner = ScenarioRunner(call_id="compound-clinical")
    runner.run([CallStarted()])
    text = f"{story}{boundary}голова болит со вчера, сейчас сильная боль."
    rich = build_rich_turn_from_text(text, utterance_id="u-canonical", engine_state=runner.state)
    assert len(rich.issue_mentions) == 1
    mention = rich.issue_mentions[0]
    assert (mention.body_site, mention.severity, mention.status) == ("голова", "сильная", "active")
    result = runner.run([text])  # canonical builder + reducer + actual playout completion
    episodes = list(runner.state.issue_episodes.values())
    assert len(episodes) == 1
    assert episodes[0].known_attributes["onset"] == "вчера"
    assert episodes[0].known_attributes["severity"] == "сильная"
    assert episodes[0].known_attributes["current"] == "сейчас"
    assert not any(s.intent.startswith("episode_headache_") for s in result.speak_effects)
    assert runner.state.delivered_question is not None
    assert runner.state.delivered_question.slot == "important_to_share"
    assert runner.state.safety_mode != "red"


@pytest.mark.parametrize("text", [
    "Голова болит со вчера.",
    "Вчера с дочерью чай пили, а голова болит со вчера.",
])
def test_canonical_sdk_present_complaint_with_old_onset_does_not_repeat_current(text):
    from packages.dialogue_engine.scenario_runner import ScenarioRunner

    runner = ScenarioRunner(call_id="present-current-proof")
    runner.run([CallStarted()])
    result = runner.run([text])
    assert not any(s.intent == "episode_headache_current" for s in result.speak_effects)
    assert any(s.intent == "episode_headache_severity" for s in result.speak_effects)
    episode = next(iter(runner.state.issue_episodes.values()))
    assert any(o.episode_id == episode.episode_id and o.temporal.current is True
               and o.evidence == "болит" for o in runner.state.observations.values())


def test_canonical_sdk_past_only_complaint_still_needs_current():
    from packages.dialogue_engine.scenario_runner import ScenarioRunner

    runner = ScenarioRunner(call_id="past-current-unknown")
    runner.run([CallStarted()])
    result = runner.run(["Голова болела вчера."])
    assert any(s.intent == "episode_headache_current" for s in result.speak_effects)


@pytest.mark.parametrize("text", [
    "У дочери голова болит со вчера, сейчас сильная боль.",
    "У дочери голова болит со вчера а сейчас сильная боль.",
    "С дочерью смотрели фильм, а голова болит у героини со вчера, сейчас сильная боль.",
    "С дочерью смотрели фильм а голова болит у героини со вчера, сейчас сильная боль.",
    "Вчера с дочерью чай пили, а голова болит со вчера, шучу.",
    "Вчера с дочерью чай пили а голова болит со вчера, шучу.",
])
def test_story_pivot_exception_keeps_other_person_fiction_and_joke_guards(text):
    result = interpret(text, utterance_id="u-falseworld")
    assert not any(o.subject == SubjectKind.SPEAKER and o.attribute == "issue"
                   for o in result.observations)


@pytest.mark.parametrize("proof", [
    "absent", "other_episode", "other_person", "superseded", "unconfirmed",
    "missing_source", "missing_evidence",
])
def test_legacy_active_default_does_not_satisfy_past_current_without_owned_proof(proof):
    from packages.dialogue_engine.product.planner import next_product_need
    from packages.dialogue_engine.semantic_kernel.types import Observation, TemporalFrame
    from packages.dialogue_engine.state import IssueEpisode

    episode = IssueEpisode(
        episode_id="ep-past", primary_label="голова болела", kind="symptom",
        body_site="голова", known_attributes={"onset": "вчера", "current": "active"},
    )
    state = EngineState(call_id="legacy-current", active_episode_id=episode.episode_id,
                        issue_episodes={episode.episode_id: episode})
    if proof != "absent":
        obs = Observation(
            observation_id="proof",
            episode_id="other" if proof == "other_episode" else episode.episode_id,
            attribute="issue", value="голова болит",
            evidence="" if proof == "missing_evidence" else "болит",
            source_turn_id="" if proof == "missing_source" else "u-grounded",
            subject=SubjectKind.OTHER_PERSON if proof == "other_person" else SubjectKind.SPEAKER,
            temporal=TemporalFrame(current=True),
            status=("superseded" if proof == "superseded" else
                    "candidate" if proof == "unconfirmed" else "confirmed"),
        )
        state.observations = {obs.observation_id: obs}
    need = next_product_need(state, episode)
    assert need is not None and need.attribute == "current"
