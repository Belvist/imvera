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
    assert "её можно терпеть или она очень сильная" in text
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


@pytest.mark.parametrize("answer,strong", [
    ("Можно терпеть.", False), ("Терпеть могу.", False),
    ("Я пока могу терпеть.", False), ("Не могу терпеть.", True),
    ("Терпеть не могу.", True),
])
def test_endurance_answer_fills_only_the_delivered_severity(answer, strong):
    runner = started("Голова болит.", "Сегодня.")
    ep_id = runner.state.active_episode_id
    result = runner.run([answer])
    ep = runner.state.issue_episodes[ep_id]
    assert ep.known_attributes["severity"].rstrip(".") in answer
    assert "голова болит сильно или терпимо" not in speech(result).lower()
    assert ep.known_attributes.get("current") != "resolved"
    if not strong:
        assert "сейчас терпимо" in speech(result).lower()
    assert runner.state.pending_episode_attribute != "severity"


@pytest.mark.parametrize("answer", [
    "Могу терпеть шум.", "Мужа могу терпеть.", "Не могу терпеть соседей.",
    "Не знаю, могу терпеть или нет.", "У мужа можно терпеть.",
])
def test_endurance_requires_a_clinical_owner_not_another_object(answer):
    runner = started("Голова болит.", "Сегодня.")
    ep_id = runner.state.active_episode_id
    runner.run([answer])
    assert not runner.state.issue_episodes[ep_id].known_attributes.get("severity")
    assert runner.state.issue_episodes[ep_id].known_attributes.get("current") != "resolved"


@pytest.mark.parametrize("complaint", [
    "Голова болит уже две недели, но терпимо.",
    "Голова болит уже две недели, терпеть могу.",
    "Голова болит уже две недели, но пока терпимо.",
])
def test_complete_elliptical_answer_needs_no_severity_reask(complaint):
    runner = started()
    result = runner.run([complaint])
    ep = next(ep for ep in runner.state.issue_episodes.values() if ep.body_site == "голова")
    assert "две недели" in ep.known_attributes["duration"]
    assert ep.known_attributes.get("severity")
    assert runner.state.pending_episode_attribute is None
    assert not any(e.intent == "episode_severity" for e in result.speak_effects)


@pytest.mark.parametrize("complaint", [
    "Голова болит, но мужа могу терпеть.",
    "Голова болит, но сосед громко говорит.",
    "Голова болит и руки ноют, но терпимо.",
    "Голова болит, но не знаю, терпимо ли.",
    "Голова не болит, но терпимо.",
])
def test_elliptical_degree_does_not_guess_its_owner(complaint):
    from packages.dialogue_engine.semantic_kernel.kernel import interpret
    from packages.dialogue_engine.semantic_kernel.types import RelationType

    meaning = interpret(complaint, utterance_id="ambiguous-degree")
    assert not any(r.type == RelationType.SEVERITY_OF for r in meaning.relations)


@pytest.mark.parametrize("request_text", ["Не понимаю вопрос.", "Что значит терпимая?"])
def test_meaning_repair_defines_degree_and_keeps_the_same_obligation(request_text):
    runner = started("Голова болит.", "Сегодня.")
    delivered = runner.state.delivered_question
    ep_id = runner.state.active_episode_id
    facts = dict(runner.state.issue_episodes[ep_id].known_attributes)
    turn = build_rich_turn_from_text(
        request_text, utterance_id="meaning", engine_state=runner.state
    )
    assert turn.dialogue_act == "repair" and not turn.answers_pending_question
    text = speech(runner.run([request_text])).lower()
    assert "можно терпеть" in text and "головную боль" in text and text.count("?") == 1
    assert runner.state.delivered_question.question_id == delivered.question_id
    assert runner.state.pending_episode_attribute == "severity"
    assert runner.state.issue_episodes[ep_id].known_attributes == facts
    runner.run(["Можно терпеть."])
    assert runner.state.issue_episodes[ep_id].known_attributes.get("severity")


@pytest.mark.parametrize("request_text", [
    "Давайте про руки.", "Давайте сначала про руки.",
    "Давайте лучше про руки.", "Давайте поговорим про руки.",
])
def test_topic_request_switches_without_fabricating_recovery(request_text):
    runner = started("Голова болит и руки ноют.")
    head = runner.state.active_episode_id
    hands = next(
        ep.episode_id for ep in runner.state.issue_episodes.values() if ep.body_site == "рука"
    )
    facts = dict(runner.state.issue_episodes[head].known_attributes)
    turn = build_rich_turn_from_text(request_text, utterance_id="topic", engine_state=runner.state)
    assert turn.dialogue_act == "question" and not turn.answers_pending_question
    assert not turn.observations and not turn.goal_facts and not turn.issue_mentions
    text = speech(runner.run([request_text])).lower()
    assert runner.state.active_episode_id == hands
    assert runner.state.pending_episode_attribute == "onset"
    assert "руки" in text and text.count("?") == 1
    assert head in runner.state.pending_episode_ids
    assert runner.state.issue_episodes[head].known_attributes == facts
    runner.run(["Сегодня."])
    assert runner.state.active_episode_id == head
    assert runner.state.pending_episode_attribute in ("onset", "duration")
    assert not runner.state.issue_episodes[head].known_attributes.get("severity")


@pytest.mark.parametrize("request_text", ["Давайте лучше про работу.", "Давайте лучше про ноги."])
def test_unknown_requested_topic_does_not_resolve_or_create_symptoms(request_text):
    runner = started("Голова болит.")
    ep_id = runner.state.active_episode_id
    runner.run([request_text])
    assert len(runner.state.issue_episodes) == 1
    assert runner.state.issue_episodes[ep_id].known_attributes.get("current") != "resolved"
    assert not runner.state.issue_episodes[ep_id].known_attributes.get("severity")


def test_topic_request_cannot_override_urgent_guard():
    runner = started("Голова болит и руки ноют.", "Не могу дышать.")
    result = runner.run(["Давайте лучше про руки."])
    assert not any("давайте сначала об этом" in e.text.lower() for e in result.speak_effects)
    assert runner.state.check_path.value == "urgent"


@pytest.mark.parametrize("answer", ["Не знаю, могу терпеть.", "Не уверен, терпеть могу."])
def test_uncertain_endurance_is_not_a_confirmed_degree(answer):
    runner = started("Голова болит.", "Сегодня.")
    ep_id = runner.state.active_episode_id
    runner.run([answer])
    assert not runner.state.issue_episodes[ep_id].known_attributes.get("severity")


@pytest.mark.parametrize("request_text", [
    "Что значит терпимая, голова болит сильно.",
    "Не понимаю вопрос, руки трясутся.",
])
def test_meaning_request_does_not_erase_a_same_turn_symptom(request_text):
    from packages.dialogue_engine.semantic_kernel.kernel import interpret

    meaning = interpret(request_text, utterance_id="mixed-request")
    assert meaning.route != "kernel_l0"
    assert meaning.observations


@pytest.mark.parametrize("request_text", [
    "Не понимаю вопрос.", "Что значит терпимая?", "Давайте лучше про руки.",
])
def test_sdk_answer_vote_cannot_replace_a_clear_conversational_request(request_text):
    from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
    from packages.dialogue_engine.turn_understanding import TurnUnderstandingV2

    runner = started("Голова болит и руки ноют.", "Сегодня.")
    turn = build_rich_turn_from_text(
        request_text, utterance_id="request-vote", engine_state=runner.state
    )
    candidate = SemanticTurn(
        act=SemanticAct.ANSWER, source_quote=request_text, confidence=0.99,
    )
    actual, used, reason = TurnUnderstandingV2().apply_act_candidate(
        turn, candidate, confident=True, engine_state=runner.state,
    )
    assert actual == turn and not used
    assert reason in ("deterministic_repair_wins", "protected_control_risk_or_question")
    assert not actual.answers_pending_question


def test_topic_request_abstains_between_two_issues_at_the_same_site():
    runner = started("Голова болит и руки ноют.", "Руки трясутся.")
    head = runner.state.active_episode_id
    turn = build_rich_turn_from_text(
        "Давайте лучше про руки.", utterance_id="ambiguous-topic", engine_state=runner.state,
    )
    assert not turn.semantic_relations and not turn.observations
    runner.run(["Давайте лучше про руки."])
    assert runner.state.issue_episodes[head].known_attributes.get("current") != "resolved"
    assert not runner.state.issue_episodes[head].known_attributes.get("severity")
    assert len([ep for ep in runner.state.issue_episodes.values() if ep.body_site == "рука"]) == 2


def test_actual_improvement_still_resolves_the_clinical_episode():
    runner = started("Голова болит.")
    ep_id = runner.state.active_episode_id
    runner.run(["Сейчас уже лучше."])
    assert runner.state.issue_episodes[ep_id].known_attributes["current"] == "resolved"


@pytest.mark.parametrize("inputs", [
    ("Руки болят уже две недели.", "Руки трясутся со вчера сильно."),
    ("Руки болят уже две недели, руки трясутся со вчера сильно.",),
])
def test_same_site_distinct_issues_own_their_values_and_recap(inputs):
    from packages.dialogue_engine.questions import concern_summary_phrase

    runner = started(*inputs)
    hands = [ep for ep in runner.state.issue_episodes.values() if ep.body_site == "рука"]
    assert len(hands) == 2
    episodes = {
        "pain": next(ep for ep in hands if "бол" in ep.primary_label),
        "tremor": next(ep for ep in hands if "тряс" in ep.primary_label),
    }
    assert episodes["pain"].episode_id != episodes["tremor"].episode_id
    assert "две недели" in str(episodes["pain"].known_attributes)
    assert not episodes["pain"].known_attributes.get("severity")
    assert "сильно" in episodes["tremor"].known_attributes["severity"]
    assert "вчера" in str(episodes["tremor"].known_attributes)
    recap = concern_summary_phrase(runner.state)
    assert "болят" in recap and "тряс" in recap


def test_pain_paraphrase_updates_the_same_owner_without_another_episode():
    runner = started("Руки болят.", "Руки ноют со вчера.")
    assert len(runner.state.issue_episodes) == 1
    ep = next(iter(runner.state.issue_episodes.values()))
    assert "вчера" in str(ep.known_attributes)


@pytest.mark.parametrize("complaint", ["Горло першит.", "Руки дрожат."])
def test_nonpain_predicate_does_not_acquire_a_fabricated_pain_label(complaint):
    runner = started(complaint)
    assert len(runner.state.issue_episodes) == 1
    labels = [m.label for ep in runner.state.issue_episodes.values() for m in ep.mentions]
    assert not any("болит" in label or "болят" in label for label in labels)


def test_other_person_at_same_site_cannot_fill_callers_clinical_value():
    runner = started("Руки болят.")
    ep_id = runner.state.active_episode_id
    runner.run(["У мужа руки болят сильно со вчера."])
    ep = runner.state.issue_episodes[ep_id]
    assert ep.subject == "speaker"
    assert not ep.known_attributes.get("severity")
    assert "вчера" not in str(ep.known_attributes)


def test_custom_mission_topic_switch_keeps_its_suspended_goal():
    engine = DialogueEngine(
        call_id="custom-topic",
        mission=CallMission(mission_id="shopping", goals=(GoalDefinition(
            goal_id="items", prompt_hint="Какие продукты вам купить?",
            answer_type="free_text", allowed_values=(),
        ),)),
    )

    def deliver():
        while (effect := engine.pop_speak_effect()) is not None:
            engine.on_playout_completed(effect.generation, effect.question_id)

    engine.start()
    deliver()
    for index, text in enumerate(("Голова болит и руки ноют.", "Давайте лучше про руки.")):
        uid = f"custom-topic-{index}"
        before = engine.state.suspended_obligation
        engine.on_user_turn(uid, text, rich_turn=engine.build_rich_turn(text, utterance_id=uid))
        deliver()
        if index:
            assert before is not None
            assert engine.state.suspended_obligation == before
    assert engine.state.goals["items"].answer is None
    assert engine.state.issue_episodes[engine.state.active_episode_id].body_site == "рука"
    assert not any(ep.known_attributes.get("current") == "resolved"
                   for ep in engine.state.issue_episodes.values())
