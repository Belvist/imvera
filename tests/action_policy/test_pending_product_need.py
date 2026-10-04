"""A canonical pending obligation is not limited to the generic four needs."""
import pytest

from packages.dialogue_engine.action_policy.actions import ActionKind
from packages.dialogue_engine.action_policy.bridge import to_response_plan
from packages.dialogue_engine.action_policy.need_value import currently_askable_needs
from packages.dialogue_engine.action_policy.needs import ASKABLE_NEEDS, normalize_attribute
from packages.dialogue_engine.action_policy.policy import choose, generate_candidates
from packages.dialogue_engine.action_policy.snapshot import (
    EpisodeSnapshot,
    PolicySnapshot,
    TurnContextView,
    build_policy_snapshot,
)
from packages.dialogue_engine.product.issue_plans import FAMILY_PLANS
from packages.dialogue_engine.question_context import QuestionNeed
from packages.dialogue_engine.state import EngineState, IssueEpisode, Question

PRODUCT_NEEDS = sorted({step for steps in FAMILY_PLANS.values() for step in steps
                        if normalize_attribute(step) not in ASKABLE_NEEDS})


def pending_snapshot(need):
    return PolicySnapshot(
        episodes=(EpisodeSnapshot("e1", "symptom", "open", known_attributes=(
            ("duration", "со вчера"), ("current", "active"),
            ("severity", "moderate"), ("functional_impact", "none"),
        )),), active_episode_id="e1", pending_episode_attribute=need,
        wellness_entry_covered=True,
    )


@pytest.mark.parametrize("need", PRODUCT_NEEDS)
def test_exact_pending_product_need_competes_and_preserves_response_meaning(need):
    snapshot = pending_snapshot(need)
    before = repr(snapshot)
    assert snapshot.outstanding_pending_obligation()
    assert ("e1", need) in currently_askable_needs(snapshot)
    assert snapshot.best_remaining_ask_utility() > 0
    decision = choose(snapshot, TurnContextView())
    assert decision.chosen.kind == ActionKind.ASK_EPISODE
    assert decision.chosen.episode_id == "e1"
    assert decision.chosen.question_need == QuestionNeed.for_attribute(need)
    plan = to_response_plan(decision, snapshot)
    assert plan.episode_id == "e1" and plan.question_needs == [QuestionNeed.for_attribute(need)]
    assert plan.marks_question
    assert repr(snapshot) == before


@pytest.mark.parametrize("need", PRODUCT_NEEDS)
def test_delivered_semantic_need_is_not_reinterpreted_from_intent_name(need):
    state = EngineState(call_id="product-need")
    state.issue_episodes["e1"] = IssueEpisode(
        episode_id="e1", primary_label="боль", kind="symptom", subject="speaker",
        known_attributes={"duration": "со вчера", "current": "active"},
    )
    state.active_episode_id = "e1"
    state.pending_episode_attribute = need
    state.delivered_question = Question(
        question_id="heard-1", slot="episode_e1", text="Вопрос",
        intent="unrelated_generic_status", episode_id="e1",
        semantic_need=QuestionNeed.for_attribute(need),
    )
    before = state.model_dump(mode="json")
    snapshot = build_policy_snapshot(state)
    assert snapshot.last_delivered_question_need == need
    assert state.model_dump(mode="json") == before


@pytest.mark.parametrize("context,kind", [
    (TurnContextView(turn_risk_level="urgent"), ActionKind.SAFETY),
    (TurnContextView(control="stop_call", dialogue_act="goodbye"), ActionKind.GOODBYE_FINAL),
    (TurnContextView(user_question=True), ActionKind.ANSWER_USER),
    (TurnContextView(dialogue_act="repair"), ActionKind.REPAIR),
])
def test_pending_product_need_never_steals_safety_control_question_or_repair(context, kind):
    decision = choose(pending_snapshot("associated"), context)
    assert decision.chosen.kind == kind


@pytest.mark.parametrize("status,subject,known", [
    ("resolved", True, ()), ("open", False, ()),
    ("open", True, (("associated", "нет"),)),
])
def test_settled_or_other_person_need_cannot_generate_an_ask(status, subject, known):
    snapshot = PolicySnapshot(
        episodes=(EpisodeSnapshot("e1", "symptom", status,
                                  speaker_owned=subject, known_attributes=known),),
        active_episode_id="e1", pending_episode_attribute="associated",
        wellness_entry_covered=True,
    )
    assert not any(action.kind == ActionKind.ASK_EPISODE
                   and action.question_need == QuestionNeed.for_attribute("associated")
                   for action in generate_candidates(snapshot, TurnContextView()))


def test_absent_pending_need_is_not_manufactured_from_product_catalog():
    snapshot = pending_snapshot(None)
    assert not any(action.kind == ActionKind.ASK_EPISODE
                   for action in generate_candidates(snapshot, TurnContextView()))


@pytest.mark.parametrize("field", ["planned_question", "playing_question"])
def test_generated_or_playing_question_is_not_reported_as_heard_need(field):
    state = EngineState(call_id="unheard-need")
    setattr(state, field, Question(
        question_id="q-unheard", slot="episode_e1", text="Вопрос",
        intent="episode_duration", episode_id="e1",
        semantic_need=QuestionNeed.for_attribute("duration"),
    ))
    snapshot = build_policy_snapshot(state)
    assert snapshot.last_question_id == "q-unheard"
    assert snapshot.last_delivered_question_need is None and snapshot.last_question_need is None
