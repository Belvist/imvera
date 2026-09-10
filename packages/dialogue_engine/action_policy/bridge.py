"""Offline bridge between ActionPolicy and existing ResponsePlan/legacy scheduler."""

from __future__ import annotations

from packages.dialogue_engine import questions
from packages.dialogue_engine.action_policy.actions import (
    ActionKey,
    ActionKind,
    CandidateAction,
    normalize_need,
)
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot
from packages.dialogue_engine.question_context import QuestionNeed
from packages.dialogue_engine.response_plan import ResponsePlan

_IDENTITY_ANSWER = (
    "Я Вера, голосовой помощник сервиса Амвера. "
    "Звоню, чтобы узнать, как вы себя чувствуете."
)


def to_response_plan(decision, snapshot: PolicySnapshot) -> ResponsePlan:
    """Map chosen action to existing renderer contract; never writes snapshot/state."""
    action: CandidateAction = decision.chosen
    kind = action.kind
    if kind == ActionKind.SAFETY:
        return ResponsePlan(obligation="safety", action="close_urgent")
    if kind == ActionKind.GOODBYE_FINAL:
        return ResponsePlan(
            obligation="control",
            action="speak",
            mandatory_question=questions._GOODBYE_FINAL,
            intent="goodbye_final",
            marks_question=False,
        )
    if kind == ActionKind.CONTROL:
        return ResponsePlan(obligation="control", action="control", control=action.control)
    if kind == ActionKind.REPAIR:
        return ResponsePlan(
            obligation="repair",
            action="speak",
            mandatory_question="Повторите, пожалуйста.",
            intent="repair_repeat",
            marks_question=False,
        )
    if kind == ActionKind.ANSWER_USER:
        return ResponsePlan(
            obligation="answer_user_question",
            action="speak",
            answer_user_question=_IDENTITY_ANSWER,
            intent="answer_user_question",
            marks_question=False,
        )
    if kind == ActionKind.ASK_EPISODE:
        return ResponsePlan(
            obligation="continue_active_episode",
            action="speak",
            episode_id=action.episode_id,
            question_needs=[action.question_need or QuestionNeed.for_attribute("concern")],
            intent=f"action_policy_episode_{normalize_need(action.question_need) or 'concern'}",
            marks_question=True,
        )
    if kind == ActionKind.CLARIFY:
        target = action.clarify_target or "concern"
        return ResponsePlan(
            obligation="continue_active_episode",
            action="speak",
            question_needs=[QuestionNeed.for_attribute(target)],
            intent=f"probe_{target}",
            slot=f"probe_{target}",
            marks_question=True,
        )
    if kind == ActionKind.IMPORTANT_TO_SHARE:
        return ResponsePlan(
            obligation="important_to_share",
            action="speak",
            mandatory_question=questions.important_to_share_question(),
            intent="important_to_share",
            slot="important_to_share",
            marks_question=True,
        )
    if kind == ActionKind.BACKGROUND_GOAL:
        return ResponsePlan(
            obligation="background_goal",
            action="speak",
            next_slot=action.target_goal,
            intent=f"check_{action.target_goal}",
            slot=action.target_goal,
            marks_question=True,
        )
    if kind == ActionKind.SUMMARY_CLOSE:
        return ResponsePlan(
            obligation="summary_close",
            action="close_summary",
            close_reason="complete",
            marks_question=False,
        )
    if kind == ActionKind.LISTEN_META:
        return ResponsePlan(
            obligation="important_to_share",
            action="speak",
            mandatory_question=(
                "Я вас слушаю. Если хотите, можете сказать, "
                "что ещё для вас сейчас важно."
            ),
            intent="important_to_share_listen",
            marks_question=False,
        )
    return ResponsePlan(
        obligation="acknowledge_important_fact",
        action="speak",
        acknowledge="Понимаю.",
        intent="ack_only",
        marks_question=False,
    )


def legacy_plan_to_action_key(plan: ResponsePlan) -> ActionKey:
    """Normalize legacy dynamic intent names into the same comparison space."""
    intent = (plan.intent or "").lower()
    obligation = str(getattr(plan.obligation, "value", plan.obligation) or "").lower()

    if plan.action == "close_urgent" or obligation == "safety" or intent == "urgent_close":
        return ActionKey(ActionKind.SAFETY)
    if plan.action == "control":
        if plan.control == "stop_call":
            return ActionKey(ActionKind.GOODBYE_FINAL)
        return ActionKey(ActionKind.CONTROL, control=plan.control)
    if intent == "goodbye_final":
        return ActionKey(ActionKind.GOODBYE_FINAL)
    if intent == "repair_repeat" or obligation == "repair":
        return ActionKey(ActionKind.REPAIR)
    if intent == "answer_user_question" or obligation == "answer_user_question":
        return ActionKey(ActionKind.ANSWER_USER)
    if intent in {"important_to_share_listen", "listen_meta"}:
        return ActionKey(ActionKind.LISTEN_META)
    if intent == "important_to_share" or obligation == "important_to_share":
        return ActionKey(ActionKind.IMPORTANT_TO_SHARE)
    if plan.action == "close_summary" or intent == "summary" or obligation == "summary_close":
        return ActionKey(ActionKind.SUMMARY_CLOSE)
    if intent.startswith("check_") or obligation == "background_goal":
        goal = plan.next_slot or plan.slot
        if not goal and intent.startswith("check_"):
            goal = intent.removeprefix("check_")
        return ActionKey(ActionKind.BACKGROUND_GOAL, target_goal=goal)
    if intent.startswith("probe_"):
        return ActionKey(ActionKind.CLARIFY, clarify_target=intent.removeprefix("probe_"))
    if plan.question_needs:
        return ActionKey(ActionKind.ASK_EPISODE, need=normalize_need(plan.question_needs[0]))
    if intent.startswith("episode_"):
        if "severity" in intent:
            need = "severity"
        elif "current" in intent:
            need = "current"
        elif "duration" in intent or "onset" in intent:
            need = "temporal"
        else:
            need = None
        return ActionKey(ActionKind.ASK_EPISODE, need=need)
    return ActionKey(ActionKind.ACK_ONLY)
