"""Chosen questions must retain meaning through delivery and answer ingestion."""

from __future__ import annotations

import pytest

from packages.contracts.enums import FsmState
from packages.dialogue_engine.conversation_policy import _episode_plan
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import PlayoutCancelled, PlayoutCompleted
from packages.dialogue_engine.question_context import QuestionNeed
from packages.dialogue_engine.reducer import _emit_from_plan, reduce
from packages.dialogue_engine.response_plan import ResponsePlan
from packages.dialogue_engine.state import EngineState, IssueEpisode


def drain(engine):
    intents = []
    while (effect := engine.pop_speak_effect()) is not None:
        intents.append(effect.intent)
        engine.on_playout_completed(effect.generation, effect.question_id)
    return intents


def _episode_state():
    state = EngineState(call_id="plan-lifecycle", fsm_state=FsmState.DAILY_CHECK)
    ep = IssueEpisode(
        episode_id="ep-head", primary_label="головная боль", kind="symptom",
        body_site="голова", subject="speaker", status="open",
        known_attributes={"_product_family": "headache"},
    )
    state.issue_episodes[ep.episode_id] = ep
    state.active_episode_id = ep.episode_id
    return state, ep


def _complete(state, effect, **updates):
    event = PlayoutCompleted(
        generation=effect.generation, question_id=effect.question_id,
        revision=state.revision, **updates,
    )
    return reduce(state, event)[0]


def test_episode_selector_does_not_commit_pending_or_ask_accounting():
    state, ep = _episode_state()
    before = dict(ep.known_attributes)
    plan = _episode_plan(state, ep, QuestionNeed.for_attribute("onset"))
    assert plan and plan.episode_id == ep.episode_id
    assert state.pending_episode_attribute is None
    assert ep.known_attributes == before


def test_episode_need_is_bound_to_question_without_fabricating_delivery():
    state, ep = _episode_state()
    need = QuestionNeed.compound("onset", "current")
    state, effects = _emit_from_plan(state, ResponsePlan(
        episode_id=ep.episode_id, question_needs=[need], marks_question=True,
    ))
    fx = effects[0]
    q = state.playing_question
    assert q and q.question_id == fx.question_id
    assert q.episode_id == ep.episode_id
    assert q.semantic_need == need
    assert state.pending_episode_attribute == "onset"
    assert "onset" not in ep.known_attributes and "current" not in ep.known_attributes
    assert state.delivered_question is None
    assert state.goals[q.slot].delivered_attempts == 0
    state = _complete(state, fx)
    assert state.pending_episode_attribute == "onset"
    assert state.delivered_question.semantic_need == need
    assert ep.known_attributes["_product_asked:onset"] == "1"
    assert state.goals[q.slot].delivered_attempts == 1
    before = state.model_dump()
    _complete(state, fx)
    assert state.model_dump() == before


def test_cancelled_episode_question_retains_obligation_without_delivered_attempt():
    state, ep = _episode_state()
    state, effects = _emit_from_plan(
        state, _episode_plan(state, ep, QuestionNeed.for_attribute("severity")),
    )
    fx = effects[0]
    state, _ = reduce(state, PlayoutCancelled(
        generation=fx.generation, question_id=fx.question_id, revision=state.revision,
    ))
    assert state.pending_episode_attribute == "severity"
    assert "severity" not in ep.known_attributes
    assert state.delivered_question is None
    assert state.goals[fx.slot].delivered_attempts == 0
    _complete(state, fx)
    assert "severity" not in ep.known_attributes
    assert state.delivered_question is None
    assert state.goals[fx.slot].delivered_attempts == 0


@pytest.mark.parametrize("wrong_field", ["generation", "revision", "question_id"])
def test_mismatched_playout_cannot_commit_delivered_question(wrong_field):
    state, ep = _episode_state()
    state, effects = _emit_from_plan(
        state, _episode_plan(state, ep, QuestionNeed.for_attribute("severity")),
    )
    fx = effects[0]
    state.bump_revision()  # A stale positive revision; 0 is the legacy wildcard.
    fields = dict(generation=fx.generation, revision=state.revision, question_id=fx.question_id)
    fields[wrong_field] = (
        "wrong-question" if wrong_field == "question_id" else fields[wrong_field] - 1
    )
    state, _ = reduce(state, PlayoutCompleted(**fields))
    assert state.delivered_question is None
    assert state.goals[fx.slot].delivered_attempts == 0
    _complete(state, fx)
    assert state.pending_episode_attribute == "severity"
    assert ep.known_attributes["_product_asked:severity"] == "1"
    assert state.goals[fx.slot].delivered_attempts == 1


@pytest.mark.parametrize("mode", ["legacy", "shadow", "policy"])
def test_real_sdk_consumes_onset_and_severity_in_selected_mode(monkeypatch, mode):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", mode)
    monkeypatch.setenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", "1")
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "0")
    engine = DialogueEngine(call_id=f"binding-{mode}")
    engine.state.mandatory_background_goals = False
    engine.start()
    drain(engine)
    for index, text in enumerate(("Голова болит.", "С утра.", "Терпимо.")):
        rich = engine.build_rich_turn(text, utterance_id=f"u{index}")
        engine.on_user_turn(f"u{index}", text, rich_turn=rich)
        drain(engine)
        ep = engine.state.issue_episodes[engine.state.active_episode_id]
        if index == 0:
            assert engine.state.pending_episode_attribute in {"onset", "duration"}
        elif index == 1:
            assert "утра" in str(ep.known_attributes).lower()
            assert engine.state.pending_episode_attribute == "severity"
        else:
            assert ep.known_attributes.get("severity")
            assert engine.state.pending_episode_attribute != "severity"
    stats = engine.state.action_policy_router_stats
    if mode == "policy":
        assert stats.get("policy_authoritative", 0) >= 3
        assert not stats.get("policy_fallback_legacy", 0)


@pytest.mark.parametrize("mode", ["legacy", "shadow", "policy"])
def test_its_decline_is_consumed_once_after_real_sdk_delivery(monkeypatch, mode):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", mode)
    monkeypatch.setenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", "1")
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "0")
    engine = DialogueEngine(call_id=f"its-binding-{mode}")
    engine.state.mandatory_background_goals = False
    engine.start()
    drain(engine)
    for index, text in enumerate(("Чувствую себя хорошо.", "Нет, больше ничего.")):
        rich = engine.build_rich_turn(text, utterance_id=f"u{index}")
        engine.on_user_turn(f"u{index}", text, rich_turn=rich)
        intents = drain(engine)
        if index == 0:
            assert engine.state.important_to_share_asked
            assert not engine.state.important_to_share_resolved
        else:
            assert engine.state.important_to_share_resolved
            assert "important_to_share" not in intents
            assert "summary" in intents


def test_its_cancelled_or_wrong_completion_does_not_fabricate_delivery():
    state = EngineState(call_id="its-cancel", fsm_state=FsmState.DAILY_CHECK)
    state, effects = _emit_from_plan(state, ResponsePlan(
        intent="important_to_share", slot="important_to_share", marks_question=True,
        mandatory_question="Есть что-нибудь, чем хотите поделиться?",
    ))
    fx = effects[0]
    assert state.important_to_share_asked
    assert state.delivered_question is None
    state, _ = reduce(state, PlayoutCompleted(
        generation=fx.generation, question_id="another-question", revision=state.revision,
    ))
    assert state.delivered_question is None
    state, _ = reduce(state, PlayoutCancelled(
        generation=fx.generation, question_id=fx.question_id, revision=state.revision,
    ))
    _complete(state, fx)
    assert state.delivered_question is None
    assert state.goals[fx.slot].delivered_attempts == 0


@pytest.mark.parametrize("mode", ["legacy", "shadow", "policy"])
@pytest.mark.parametrize("cancel_first", [False, True])
def test_real_early_or_interrupted_answer_retains_grounded_temporal_value(
    monkeypatch, mode, cancel_first,
):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", mode)
    monkeypatch.setenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", "1")
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "0")
    engine = DialogueEngine(call_id=f"early-{mode}-{cancel_first}")
    engine.state.mandatory_background_goals = False
    engine.start()
    drain(engine)
    text = "Голова болит."
    rich = engine.build_rich_turn(text, utterance_id="u1")
    engine.on_user_turn("u1", text, rich_turn=rich)
    fx = engine.pop_speak_effect()
    assert fx and fx.marks_question
    ep = engine.state.issue_episodes[engine.state.active_episode_id]
    assert not ep.known_attributes.get("onset")
    assert not ep.known_attributes.get("duration")
    if cancel_first:
        engine.on_playout_cancelled(fx.generation, fx.question_id)
    delivered = engine.state.delivered_question
    assert delivered is None or delivered.question_id != fx.question_id
    assert engine.state.goals[fx.slot].delivered_attempts == 0
    text = "С утра."
    rich = engine.build_rich_turn(text, utterance_id="u2")
    engine.on_user_turn("u2", text, rich_turn=rich)
    intents = drain(engine)
    assert "утра" in (ep.known_attributes.get("onset", "")
                       + ep.known_attributes.get("duration", "")).lower()
    assert "summary" not in intents
    assert engine.state.pending_episode_attribute == "severity"


def test_cancellation_for_other_question_cannot_clear_current_playout():
    state, ep = _episode_state()
    state, effects = _emit_from_plan(
        state, _episode_plan(state, ep, QuestionNeed.for_attribute("severity")),
    )
    fx = effects[0]
    state, _ = reduce(state, PlayoutCancelled(
        generation=fx.generation, question_id="old-question", revision=state.revision,
    ))
    assert state.playing_question and state.playing_question.question_id == fx.question_id
    _complete(state, fx)
    assert state.delivered_question and state.delivered_question.question_id == fx.question_id
    assert state.goals[fx.slot].delivered_attempts == 1


@pytest.mark.parametrize("mode", ["legacy", "shadow", "policy"])
@pytest.mark.parametrize("cancel_first", [False, True])
def test_early_or_interrupted_its_decline_resolves_pending_obligation(
    monkeypatch, mode, cancel_first,
):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", mode)
    monkeypatch.setenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", "1")
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "0")
    engine = DialogueEngine(call_id=f"early-its-{mode}-{cancel_first}")
    engine.state.mandatory_background_goals = False
    engine.start()
    drain(engine)
    text = "Чувствую себя хорошо."
    rich = engine.build_rich_turn(text, utterance_id="u1")
    engine.on_user_turn("u1", text, rich_turn=rich)
    fx = engine.pop_speak_effect()
    assert fx and fx.intent == "important_to_share"
    if cancel_first:
        engine.on_playout_cancelled(fx.generation, fx.question_id)
    assert engine.state.goals[fx.slot].delivered_attempts == 0
    text = "Нет, больше ничего."
    rich = engine.build_rich_turn(text, utterance_id="u2")
    engine.on_user_turn("u2", text, rich_turn=rich)
    intents = drain(engine)
    assert engine.state.important_to_share_resolved
    assert "summary" in intents
    assert "important_to_share" not in intents
    assert engine.state.goals[fx.slot].delivered_attempts == 0
