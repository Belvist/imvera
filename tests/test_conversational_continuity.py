"""Conversation stays connected to accepted evidence and the delivered question."""

import pytest

from packages.dialogue_engine.conversation_policy import (
    _bridge_ack_for_episode,
    _grounded_ack_for_mentions,
)
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.mission import CallMission, GoalDefinition
from packages.dialogue_engine.questions import wellness_ack
from packages.dialogue_engine.response_plan import ResponsePlan, compose_speech
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import EngineState, IssueEpisode
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine


def started(*steps):
    runner = ScenarioRunner(call_id="conversation-test")
    runner.run([CallStarted(), *steps])
    return runner


def speech(result):
    return " ".join(effect.text for effect in result.speak_effects)


def test_two_complaints_get_one_connected_acknowledgment():
    runner = started()
    text = speech(runner.run(["Голова болит и руки ноют."]))
    assert "голова болит и руки ноют" in text.lower()
    assert "по порядку" in text.lower()
    assert "учла" not in text.lower() and "записала" not in text.lower()
    assert text.count("?") == 1
    assert sorted(ep.body_site for ep in runner.state.issue_episodes.values()) == ["голова", "рука"]
    assert runner.state.pending_episode_attribute == "duration"
    assert not any(
        ep.known_attributes.get("duration") for ep in runner.state.issue_episodes.values()
    )


@pytest.mark.parametrize(
    "answer,quantity",
    [
        ("Это уже две недели продолжается так.", "две недели"),
        ("Уже три дня.", "три дня"),
        ("Это длится 2 недели.", "2 недели"),
    ],
)
def test_temporal_answer_is_heard_before_a_named_followup(answer, quantity):
    runner = started("Голова болит.")
    episode_id = runner.state.active_episode_id
    text = speech(runner.run([answer])).lower()
    assert f"продолжается уже {quantity}" in text
    assert "голова болит сильно или терпимо" in text
    assert text.count("?") == 1
    assert quantity in runner.state.issue_episodes[episode_id].known_attributes["duration"].lower()
    assert not runner.state.issue_episodes[episode_id].known_attributes.get("severity")


@pytest.mark.parametrize(
    "answer",
    [
        "Не помню, две недели или месяц.",
        "Две недели принимаю таблетки.",
        "Буду дома две недели.",
        "У мужа это длится две недели.",
    ],
)
def test_quantity_without_accepted_ownership_gets_no_temporal_ack(answer):
    runner = started("Голова болит.")
    episode_id = runner.state.active_episode_id
    text = speech(runner.run([answer])).lower()
    assert "продолжается уже" not in text
    assert not runner.state.issue_episodes[episode_id].known_attributes.get("duration")


def test_new_symptom_is_heard_without_losing_the_named_pending_question():
    runner = started("Голова болит и руки ноют.", "Это уже две недели.")
    episode_id = runner.state.active_episode_id
    text = speech(runner.run(["Руки постоянно трясутся."])).lower()
    assert "руки трясутся" in text
    assert "голова болит сильно или терпимо" in text
    assert text.count("?") == 1
    assert "записала" not in text and "учла" not in text
    assert runner.state.active_episode_id == episode_id
    assert not runner.state.issue_episodes[episode_id].known_attributes.get("severity")
    assert any(
        "тряс" in m.label for ep in runner.state.issue_episodes.values() for m in ep.mentions
    )


@pytest.mark.parametrize(
    "request_text",
    [
        "Уточните вопрос.",
        "Конкретизируйте вопрос.",
        "Конкретнись и по поводу первого.",
        "Не поняла.",
    ],
)
def test_explanation_names_the_question_without_replaying_old_ack(request_text):
    runner = started("Голова болит.", "Две недели.", "Руки трясутся.")
    delivered = runner.state.delivered_question
    episode_id = runner.state.active_episode_id
    facts = {eid: dict(ep.known_attributes) for eid, ep in runner.state.issue_episodes.items()}
    turn = build_rich_turn_from_text(
        request_text, utterance_id="explain", engine_state=runner.state
    )
    assert turn.dialogue_act == "repair" and not turn.answers_pending_question
    result = runner.run([request_text])
    text = speech(result).lower()
    assert "я спрашиваю про головную боль" in text
    assert "голова болит сильно или терпимо" in text
    assert "руки" not in text and "записала" not in text and "да, слышу" not in text
    assert text.count("?") == 1
    assert any(effect.intent == "repair_repeat" for effect in result.speak_effects)
    assert runner.state.delivered_question.question_id == delivered.question_id
    assert runner.state.active_episode_id == episode_id
    assert runner.state.pending_episode_attribute == "severity"
    assert {eid: ep.known_attributes for eid, ep in runner.state.issue_episodes.items()} == facts


@pytest.mark.parametrize("request_text", ["Повторите, пожалуйста.", "Не расслышала."])
def test_hearing_repeat_preserves_actual_delivered_words(request_text):
    runner = started("Голова болит.", "Две недели.")
    delivered = runner.state.delivered_question
    result = runner.run([request_text])
    assert delivered.text in speech(result)
    assert "Я спрашиваю про" not in speech(result)
    assert runner.state.delivered_question.question_id == delivered.question_id
    assert not runner.state.issue_episodes[runner.state.active_episode_id].known_attributes.get(
        "severity"
    )


@pytest.mark.parametrize("complaint", ["Голова болит.", "Живот болит и тошнит."])
def test_empathy_does_not_make_someone_elses_symptoms_the_callers(complaint):
    turn = build_rich_turn_from_text(complaint, utterance_id="other")
    assert turn.issue_mentions
    # Canonical candidates from another semantic provider must respect the
    # same subject boundary as the local kernel's other-person observations.
    turn = turn.model_copy(
        update={
            "issue_mentions": tuple(
                mention.model_copy(update={"subject": "other_person"})
                for mention in turn.issue_mentions
            )
        }
    )
    assert _grounded_ack_for_mentions(turn) == ""


def test_past_only_report_does_not_gain_a_present_tense_complaint():
    turn = build_rich_turn_from_text("Голова болела вчера.", utterance_id="past")
    assert turn.issue_mentions
    ack = _grounded_ack_for_mentions(turn).lower()
    assert "голова болит" not in ack
    assert "полегчало" not in ack and "проходит" not in ack


def test_positive_wellness_gets_one_sincere_reaction():
    assert wellness_ack(polarity="positive", value="Хорошо.") == "Рада это слышать."
    runner = started()
    text = speech(runner.run(["Я чувствую себя хорошо."])).lower()
    assert "рада это слышать" in text
    assert "очень хорошо" not in text
    assert text.count("?") == 1


def test_new_acknowledgment_is_idempotent_and_does_not_write_facts():
    state = EngineState(call_id="render-conversation")
    before = state.model_dump()
    plan = ResponsePlan(
        acknowledgement_kind="temporal_answer",
        acknowledgement_value="две недели",
        mandatory_question="Сейчас голова болит сильно или терпимо?",
        marks_question=True,
    )
    text = compose_speech(plan, state)
    assert compose_speech(plan, state) == text
    assert text.count("две недели") == 1
    assert state.model_dump() == before


@pytest.mark.parametrize(
    "complaint",
    [
        "Уточните вопрос, не могу дышать.",
        "Не хочу разговаривать, не могу дышать.",
    ],
)
def test_safety_bypasses_conversational_delivery(complaint):
    runner = started("Голова болит.")
    result = runner.run([complaint])
    assert result.speak_effects[-1].intent == "urgent_close"
    assert runner.state.closing_reason == "urgent"
    assert "продолжается уже" not in speech(result)
    assert "я спрашиваю" not in speech(result).lower()


def test_refusal_is_question_free_without_a_sympathetic_followup():
    runner = started("Голова болит.")
    result = runner.run(["Не хочу разговаривать."])
    assert "?" not in speech(result)
    assert runner.state.closing_reason == "revoke_consent"


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Сильно.", "сильную боль тяжело переносить"),
        ("Терпимая.", "сейчас терпимо"),
    ],
)
def test_accepted_severity_gets_a_reaction_without_new_clinical_facts(answer, expected):
    runner = started("Голова болит.", "Сегодня.")
    episode_id = runner.state.active_episode_id
    text = speech(runner.run([answer])).lower()
    assert expected in text
    assert (
        runner.state.issue_episodes[episode_id].known_attributes["severity"].lower()
        == answer.lower()
    )
    assert "всё хорошо" not in text and "полегчало" not in text


def test_episode_handoff_names_the_next_topic_without_praising_pain():
    runner = started("Голова болит и руки ноют.", "Сегодня.")
    text = speech(runner.run(["Терпимая."])).lower()
    assert "теперь про руки" in text
    assert not text.startswith("хорошо")
    assert text.count("?") == 1
    assert runner.state.issue_episodes[runner.state.active_episode_id].body_site == "рука"


def test_naming_a_head_site_does_not_turn_dizziness_into_pain():
    episode = IssueEpisode(
        episode_id="dizzy",
        primary_label="головокружение",
        kind="symptom",
        body_site="голова",
    )
    before = episode.model_dump()
    text = _bridge_ack_for_episode(episode).lower()
    assert "головокружение" in text
    assert "боль" not in text
    assert episode.model_dump() == before


def test_custom_mission_explains_health_interrupt_without_answering_its_goal():
    engine = DialogueEngine(
        call_id="custom-explanation",
        mission=CallMission(
            mission_id="shopping",
            goals=(
                GoalDefinition(
                    goal_id="items",
                    prompt_hint="Какие продукты вам купить?",
                    answer_type="free_text",
                    allowed_values=(),
                ),
            ),
        ),
    )

    def deliver():
        effects = []
        while (effect := engine.pop_speak_effect()) is not None:
            effects.append(effect)
            engine.on_playout_completed(effect.generation, effect.question_id)
        return effects

    engine.start()
    deliver()
    for seq, text in enumerate(("Голова болит.", "Две недели.", "Уточните вопрос.")):
        uid = f"custom-{seq}"
        turn = engine.build_rich_turn(text, utterance_id=uid)
        engine.on_user_turn(uid, text, rich_turn=turn)
        effects = deliver()
        if text == "Две недели.":
            assert "продолжается уже две недели" in effects[-1].text
    assert "Я спрашиваю про головную боль" in effects[-1].text
    assert effects[-1].text.count("?") == 1
    assert engine.state.goals["items"].answer is None
    assert not any(
        ep.known_attributes.get("severity") for ep in engine.state.issue_episodes.values()
    )
