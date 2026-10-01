"""SDK regressions exercise text → canonical turn → reducer, not injected facts."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.mission import CallMission, GoalDefinition
from packages.dialogue_engine.mission_result import build_mission_result
from packages.dialogue_engine.state import GoalLifecycle

pytestmark = pytest.mark.dialogue_engine


def deliver(engine: DialogueEngine) -> list:
    spoken = []
    while (effect := engine.pop_speak_effect()) is not None:
        spoken.append(effect)
        engine.on_playout_completed(effect.generation, effect.question_id)
    return spoken


def reply(engine: DialogueEngine, text: str, uid: str = "u") -> list:
    engine.on_user_turn(uid, text, rich_turn=engine.build_rich_turn(text, utterance_id=uid))
    return deliver(engine)


@pytest.mark.parametrize("full", [False, True])
def test_volunteered_facts_satisfy_goals_with_evidence(full: bool) -> None:
    engine = DialogueEngine(call_id="all-facts")
    engine.state.mandatory_background_goals = full
    engine.start()
    deliver(engine)
    text = "Чувствую себя хорошо. Настроение хорошее. Спал хорошо. Сегодня буду дома."
    reply(engine, text)
    result = build_mission_result(engine.state)
    assert result.status == "COMPLETED"
    for goal in result.goals:
        assert goal.lifecycle == GoalLifecycle.SATISFIED.value, goal
        assert goal.value is not None
        assert goal.evidence and all(quote in text for quote in goal.evidence), goal


@pytest.mark.parametrize("text", ["Не помню.", "Не могу вспомнить.", "Не помню уже."])
def test_rich_not_recalled_advances_episode_without_inventing_date(text: str) -> None:
    engine = DialogueEngine(call_id="recall")
    engine.start()
    deliver(engine)
    reply(engine, "Голова болит.", "u1")
    assert engine.state.pending_episode_attribute in {"onset", "duration"}
    old_question = engine.pending_question_text()
    spoken = reply(engine, text, "u2")
    episode = engine.state.issue_episodes[engine.state.active_episode_id]
    assert episode.known_attributes.get("_temporal_skipped") == "1"
    assert not episode.known_attributes.get("onset")
    assert not episode.known_attributes.get("duration")
    assert engine.state.pending_episode_attribute not in {"onset", "duration"}
    assert all(effect.text != old_question for effect in spoken)
    assert all("unknown" != value for value in episode.known_attributes.values())


def shopping_engine() -> DialogueEngine:
    engine = DialogueEngine(
        call_id="shopping",
        mission=CallMission(
            mission_id="shopping",
            goals=(GoalDefinition(
                goal_id="items", prompt_hint="Какие продукты вам купить?",
                answer_type="free_text", allowed_values=(),
            ),),
        ),
    )
    engine.start()
    deliver(engine)
    return engine


def test_health_interruption_is_not_a_shopping_answer() -> None:
    engine = shopping_engine()
    spoken = reply(engine, "Голова болит.")
    assert engine.state.goals["items"].lifecycle != GoalLifecycle.SATISFIED
    assert engine.state.goals["items"].answer is None
    assert any(ep.body_site == "голова" for ep in engine.state.issue_episodes.values())
    assert spoken and spoken[-1].intent.startswith("episode_")
    assert all(effect.intent != "ask_mission_goal" for effect in spoken)


def test_mixed_answer_retains_only_grounded_shopping_clause() -> None:
    engine = shopping_engine()
    reply(engine, "Молока и хлеба. Сегодня сильно болит голова.")
    goal = next(g for g in build_mission_result(engine.state).goals if g.goal_id == "items")
    assert goal.lifecycle == GoalLifecycle.SATISFIED.value
    assert goal.value == "Молока и хлеба"
    assert goal.evidence == ["Молока и хлеба"]
    assert engine.state.issue_episodes


def test_declared_health_goal_accepts_health_answer() -> None:
    engine = DialogueEngine(
        call_id="health",
        mission=CallMission(mission_id="health", goals=(GoalDefinition(
            goal_id="symptoms", prompt_hint="Что вас беспокоит?",
            answer_type="free_text", allowed_values=(), semantic_scope="speaker_health",
        ),)),
    )
    engine.start()
    deliver(engine)
    reply(engine, "Сегодня сильно болит голова.")
    assert engine.state.goals["symptoms"].lifecycle == GoalLifecycle.SATISFIED


def test_correction_keeps_latest_goal_value_and_quote() -> None:
    from packages.dialogue_engine.policy import apply_slot_answer

    engine = DialogueEngine(call_id="correction")
    apply_slot_answer(engine.state, "sleep", "хорошо", source_text="Спал хорошо.", turn_id="u1")
    apply_slot_answer(
        engine.state, "sleep", "плохо", source_text="Нет, спал плохо.",
        turn_id="u2", correction=True,
    )
    goal = next(g for g in build_mission_result(engine.state).goals if g.goal_id == "sleep")
    assert goal.value == "плохо"
    assert goal.evidence == ["Нет, спал плохо."]
    assert len(engine.state.slot_corrections) == 1


def test_free_text_provider_cannot_invent_value_next_to_real_quote() -> None:
    from packages.dialogue_engine.mission import GoalAnswerCandidate
    from packages.dialogue_engine.mission_grounding import validate_goal_answer_candidate

    engine = shopping_engine()
    candidate = GoalAnswerCandidate(
        goal_id="items", value="молока и хлеба", evidence="Голова болит.", confidence=0.99,
    )
    valid, reason = validate_goal_answer_candidate(
        candidate, mission=engine.mission, utterance="Голова болит.",
    )
    assert not valid and reason == "free_text_value_not_grounded"


def test_not_recalled_severity_is_unanswered_and_never_reasked() -> None:
    engine = DialogueEngine(call_id="severity-recall")
    engine.start()
    deliver(engine)
    reply(engine, "Голова болит.", "u1")
    reply(engine, "Не помню.", "u2")
    assert engine.state.pending_episode_attribute == "severity"
    episode = engine.state.issue_episodes[engine.state.active_episode_id]
    old_question = engine.pending_question_text()
    spoken = reply(engine, "Не помню.", "u3")
    assert episode.unanswered_attributes["severity"] == "Не помню."
    assert not episode.known_attributes.get("severity")
    assert engine.state.pending_episode_attribute != "severity"
    assert all(effect.text != old_question for effect in spoken)


def test_custom_not_recalled_skips_question_without_fake_answer() -> None:
    engine = shopping_engine()
    old_question = engine.pending_question_text()
    spoken = reply(engine, "Не помню.")
    assert engine.state.goals["items"].lifecycle == GoalLifecycle.SKIPPED
    assert engine.state.goals["items"].answer is None
    assert build_mission_result(engine.state).status == "PARTIAL"
    assert all(effect.text != old_question for effect in spoken)


def test_finished_questionnaire_does_not_mean_active_symptom_is_gone() -> None:
    from packages.dialogue_engine.mission_result import build_call_outcomes
    from packages.dialogue_engine.state import IssueEpisode

    engine = DialogueEngine(call_id="active-pain")
    engine.start()
    deliver(engine)
    reply(engine, "Чувствую себя хорошо.")
    assert build_mission_result(engine.state).status == "COMPLETED"
    engine.state.call_closed = True
    engine.state.closing_reason = "goodbye"
    engine.state.issue_episodes["ep"] = IssueEpisode(
        episode_id="ep", primary_label="голова болит", kind="symptom",
        subject="speaker", status="resolved", known_attributes={"current": "active"},
    )
    assert build_call_outcomes(engine.state).candidate_family_status == "YELLOW"


def test_health_interrupt_then_resume_shopping_without_consuming_episode_answer() -> None:
    engine = shopping_engine()
    reply(engine, "Голова болит.", "u1")
    assert engine.state.suspended_obligation.goal_id == "items"
    reply(engine, "Сегодня.", "u2")
    assert engine.state.goals["items"].answer is None
    spoken = reply(engine, "Терпимая.", "u3")
    assert any(effect.intent in {"ask_mission_goal", "resume_mission_goal"} for effect in spoken)
    assert "продукты" in engine.pending_question_text().lower()
    assert engine.state.suspended_obligation is None  # Cleared only by delivered resumption.
    reply(engine, "Молока и хлеба.", "u4")
    assert engine.state.goals["items"].answer == "Молока и хлеба."
    assert engine.state.issue_episodes


@pytest.mark.parametrize("with_model", [False, True])
def test_declared_enum_unknown_retains_its_typed_answer(with_model: bool) -> None:
    from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn

    engine = DialogueEngine(call_id="enum-unknown", mission=CallMission(
        mission_id="visit", goals=(GoalDefinition(
            goal_id="visit", prompt_hint="Сегодня врач приходил?",
            answer_type="enum", allowed_values=("yes", "no", "unknown"),
        ),),
    ))
    engine.start()
    deliver(engine)
    text = "Не помню."
    candidate = SemanticTurn(
        act=SemanticAct.ANSWER, source_quote=text, confidence=0.99, not_recalled=True,
    ) if with_model else None
    turn = engine.build_rich_turn(
        text, utterance_id="u", act_candidate=candidate, candidate_confident=with_model,
    )
    engine.on_user_turn("u", text, rich_turn=turn)
    goal = engine.state.goals["visit"]
    assert goal.lifecycle == GoalLifecycle.SATISFIED
    assert goal.answer == "unknown"
    assert "Не помню." in build_mission_result(engine.state).goals[0].evidence
