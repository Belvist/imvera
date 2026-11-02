"""Grounded revisions reach the single writer before response selection."""

from __future__ import annotations

import copy

import pytest

from packages.contracts.semantic import Evidence, FactCandidate
from packages.dialogue_engine.events import CallStarted, User
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.turn_understanding import RichUserTurn, build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    for name, value in {
        "IMVERA_DIALOGUE_ENGINE": "1",
        "IMVERA_COVERAGE_LADDER": "0",
        "IMVERA_ACTION_POLICY_MODE": "off",
        "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
    }.items():
        monkeypatch.setenv(name, value)


def known_sleep():
    runner = ScenarioRunner(call_id="grounded-revision")
    from packages.dialogue_engine.mission import daily_check_mission
    from packages.dialogue_engine.mission_seed import apply_mission_to_state

    apply_mission_to_state(runner.state, daily_check_mission())
    runner.run([CallStarted(), "Самочувствие хорошее, спала хорошо."])
    return runner


@pytest.mark.parametrize("text", ["Спала плохо.", "Плохо спала.", "Спала не очень хорошо."])
def test_sleep_quality_is_not_a_general_wellness_deterioration(text):
    turn = build_rich_turn_from_text(text, utterance_id="quality", engine_state=known_sleep().state)
    assert any(f.field == "sleep" for f in turn.goal_facts)
    assert not any(f.field == "wellness" for f in turn.goal_facts)
    assert any(m.kind == "sleep_problem" and m.subject == "speaker" for m in turn.issue_mentions)


def test_explicit_sleep_revision_and_later_detail_do_not_use_old_summary():
    runner = known_sleep()
    result = runner.run(["Нет, я перепутала, спала плохо."])
    record = runner.state.slot_records["sleep"]
    assert "спала плохо" in record.value.lower()
    assert record.source_turn_id == "u-2"
    assert record.source_text in "Нет, я перепутала, спала плохо."
    assert runner.state.slot_records["wellness"].polarity == "positive"
    assert any(c["slot"] == "sleep" for c in runner.state.slot_corrections)
    assert not runner.state.call_closed
    assert result.speak_effects[-1].intent == "topic_sleep_pattern"
    result = runner.run(["Часто просыпалась."])
    assert not runner.state.call_closed
    assert all(s.intent != "goodbye_final" for s in result.speak_effects)
    assert "просыпалась" in runner.state.slot_records["sleep"].value.lower()
    assert runner.state.goals["sleep"].answer == runner.state.slot_values["sleep"]
    assert result.speak_effects[-1].intent == "topic_sleep_daytime_impact"


@pytest.mark.parametrize(
    "text",
    [
        "Дочь проснулась в четыре.",
        "Раньше проснулась в четыре.",
        "Если я часто просыпалась, то буду усталой.",
        "Дочь сказала: «Я проснулась в четыре».",
    ],
)
def test_noncaller_or_nonasserted_detail_cannot_complete_callers_sleep_pattern(text):
    runner = known_sleep()
    runner.run(["Нет, я перепутала, спала плохо."])
    before = copy.deepcopy(runner.state.topic_dimensions)
    runner.run([text])
    assert runner.state.topic_dimensions.get("sleep") == before.get("sleep")


def test_other_complaint_duration_is_not_a_sleep_pattern():
    runner = known_sleep()
    runner.run(["Нет, я перепутала, спала плохо."])
    runner.run(["Голова болит пять часов."])
    assert "pattern" not in runner.state.topic_dimensions.get("sleep", [])


def test_accepted_sleep_detail_after_summary_invalidates_its_completion_scope():
    runner = known_sleep()
    runner.run(["Нет, ничего."])
    assert runner.state.summary_delivered
    result = runner.run(["Часто просыпалась."])
    assert not runner.state.call_closed
    assert runner.state.slot_records["sleep"].source_turn_id == "u-3"
    assert result.speak_effects[-1].intent != "goodbye_final"


@pytest.mark.parametrize(
    "text",
    [
        "Дочь спала плохо.",
        "Раньше спала плохо.",
        "Год назад спала плохо.",
        "Дочь сказала: «Я спала плохо».",
        "А как я спала?",
    ],
)
def test_unowned_historical_quoted_or_question_content_does_not_revise_sleep(text):
    runner = known_sleep()
    before = copy.deepcopy(runner.state.slot_records["sleep"])
    runner.run([text])
    assert runner.state.slot_records["sleep"] == before


@pytest.mark.parametrize("invalid", ["subject", "scope", "quote", "value"])
def test_invalid_direct_proposal_cannot_revise_a_filled_fact(invalid):
    runner = known_sleep()
    text = "Спала плохо."
    data = dict(
        field="sleep",
        value=text,
        subject="speaker",
        temporal_scope="now",
        negated=False,
        evidence=Evidence(start=0, end=len(text), quote=text),
    )
    if invalid == "subject":
        data["subject"] = "other"
    elif invalid == "scope":
        data["temporal_scope"] = "past"
    elif invalid == "quote":
        data["evidence"] = Evidence(start=0, end=6, quote="Выспалась.")
    else:
        data["value"] = "Не спала три ночи."
    before = copy.deepcopy(runner.state.slot_records["sleep"])
    turn = RichUserTurn(
        utterance_id="invalid",
        raw_text=text,
        dialogue_act="answer",
        control="none",
        answers_pending_question=False,
        needs_clarification=False,
        goal_facts=(FactCandidate(**data),),
    )
    runner.run([User(text=text, rich_turn=turn)])
    assert runner.state.slot_records["sleep"] == before


@pytest.mark.parametrize(
    "text",
    [
        "Я перепутала, раньше спала плохо.",
        "Я перепутала, дочь спала плохо.",
        "Если я спала плохо, то буду усталой.",
    ],
)
def test_correction_marker_does_not_license_a_noncurrent_or_hypothetical_fact(text):
    runner = known_sleep()
    before = copy.deepcopy(runner.state.slot_records["sleep"])
    runner.run([text])
    assert runner.state.slot_records["sleep"] == before


@pytest.mark.parametrize("text", ["Раньше спала плохо.", "Дочь спала плохо."])
def test_direct_mission_correction_cannot_bypass_current_caller_grounding(text):
    from packages.dialogue_engine.mission import GoalAnswerCandidate

    runner = known_sleep()
    before = copy.deepcopy(runner.state.slot_records["sleep"])
    turn = RichUserTurn(
        utterance_id="mission-bypass",
        raw_text=text,
        dialogue_act="answer",
        control="none",
        answers_pending_question=False,
        needs_clarification=False,
        goal_answers=(
            GoalAnswerCandidate(
                goal_id="sleep", value=text, evidence=text, confidence=1, is_correction=True
            ),
        ),
    )
    runner.run([User(text=text, rich_turn=turn)])
    assert runner.state.slot_records["sleep"] == before


@pytest.mark.parametrize("text", [
    "Самочувствие хорошее, раньше спала плохо.",
    "Самочувствие хорошее, год назад спала плохо.",
])
def test_remote_history_cannot_answer_todays_unasked_sleep_question(text):
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.engine import DialogueEngine

    engine = DialogueEngine(call_id="historical-sleep")
    engine.start()
    while (speech := engine.pop_speak_effect()) is not None:
        engine.on_playout_completed(speech.generation, speech.question_id)
    turn = engine.build_rich_turn(text, utterance_id="history")
    engine.on_user_turn("history", text, rich_turn=turn)
    assert engine.state.slots["sleep"] == SlotStatus.OPEN
    assert "sleep" not in engine.state.slot_records
@pytest.mark.parametrize("mode", ["off", "policy"])
def test_default_sdk_sleep_record_cannot_be_overwritten_by_another_complaint(monkeypatch, mode):
    from packages.dialogue_engine.engine import DialogueEngine

    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", mode)
    monkeypatch.setenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", "1")
    engine = DialogueEngine(call_id="sleep-not-headache")

    def deliver():
        while (speech := engine.pop_speak_effect()) is not None:
            engine.on_playout_completed(speech.generation, speech.question_id)

    engine.start()
    deliver()
    for uid, text in (("u1", "Самочувствие хорошее, спала хорошо."),
                      ("u2", "Нет, я перепутала, спала плохо.")):
        engine.on_user_turn(uid, text, rich_turn=engine.build_rich_turn(text, utterance_id=uid))
        deliver()
    before = copy.deepcopy(engine.state.slot_records["sleep"])
    text = "Голова болит пять часов."
    engine.on_user_turn("u3", text, rich_turn=engine.build_rich_turn(text, utterance_id="u3"))
    deliver()
    assert engine.state.slot_records["sleep"] == before
    assert any(ep.body_site == "голова" for ep in engine.state.issue_episodes.values())


@pytest.mark.parametrize("text", ["Голова болит пять часов.", "Спала температура пять часов назад.",
                                  "Гуляла пять часов."])
@pytest.mark.parametrize("answer_slot", [None, "sleep"])
def test_clock_with_another_predicate_is_not_a_sleep_fact(text, answer_slot):
    from packages.dialogue_engine.issue_mention_extract import extract_goal_facts

    assert not any(f.field == "sleep" for f in extract_goal_facts(text, answer_slot=answer_slot))


@pytest.mark.parametrize("text", ["Спала три часа.", "Спала часов пять.", "Спала пять часов."])
def test_explicit_sleep_quantity_is_volunteered_sleep_evidence(text):
    from packages.dialogue_engine.issue_mention_extract import extract_goal_facts

    assert any(f.field == "sleep" and f.value == text for f in extract_goal_facts(text))


def test_bare_hours_need_sleep_question_context():
    from packages.dialogue_engine.issue_mention_extract import extract_goal_facts

    assert not any(f.field == "sleep" for f in extract_goal_facts("Пять часов."))
    assert any(f.field == "sleep" for f in extract_goal_facts("Пять часов.", answer_slot="sleep"))

