"""Primary safety/answer/repair action outranks its secondary listening context."""

import pytest

from packages.dialogue_engine.action_policy.actions import ActionKind
from packages.dialogue_engine.action_policy.bridge import legacy_plan_to_action_key
from packages.dialogue_engine.response_plan import ResponsePlan, render_response_plan
from packages.dialogue_engine.state import EngineState


@pytest.mark.parametrize("kwargs,kind", [
    ({"action": "close_urgent", "obligation": "safety"}, ActionKind.SAFETY),
    ({"action": "control", "control": "stop_call"}, ActionKind.GOODBYE_FINAL),
    ({"intent": "repair_repeat", "obligation": "repair"}, ActionKind.REPAIR),
    ({"intent": "answer_user_question", "answer_user_question": "У меня нет ответа."},
     ActionKind.ANSWER_USER),
])
def test_primary_action_not_normalized_as_listener(kwargs, kind):
    plan = ResponsePlan(thread_mode="listen", **kwargs)
    assert legacy_plan_to_action_key(plan).kind == kind


def test_thread_metadata_cannot_override_urgent_speech():
    state = EngineState(call_id="safe")
    plan = render_response_plan(ResponsePlan(action="close_urgent", thread_mode="listen"), state)
    assert plan.intent == "urgent_close" and not plan.marks_question
    assert "слушаю" not in plan.mandatory_question.lower()
