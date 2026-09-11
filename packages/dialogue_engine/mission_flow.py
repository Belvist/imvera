"""Custom CallMission flow helpers used by conversation_policy (not a second engine)."""

from __future__ import annotations

from packages.dialogue_engine.mission import CallMission, GoalDefinition, definition_by_id
from packages.dialogue_engine.mission_seed import mission_from_state
from packages.dialogue_engine.response_plan import ResponsePlan
from packages.dialogue_engine.state import (
    EngineState,
    GoalLifecycle,
    SuspendedObligation,
)

_TERMINAL = frozenset(
    {
        GoalLifecycle.SATISFIED,
        GoalLifecycle.DECLINED,
        GoalLifecycle.SKIPPED,
        GoalLifecycle.NOT_APPLICABLE,
        GoalLifecycle.BLOCKED,
    }
)

_FINAL_OPEN = "Хотите ещё что-то добавить?"
_HOUSEHOLD_HELP = (
    "С этим сейчас нужна помощь близких или вы пока справляетесь?"
)
_IDENTITY = "Я Вера, голосовой помощник сервиса Амвера."


def is_custom_mission(state: EngineState) -> bool:
    return (state.mission_preset or "") != "daily_check" and bool(state.mission_goal_ids)


def mission_catalog(state: EngineState) -> CallMission:
    return mission_from_state(state)


def unresolved_required_goals(state: EngineState) -> list[tuple[GoalDefinition, object]]:
    mission = mission_catalog(state)
    pairs: list[tuple[GoalDefinition, object]] = []
    for gdef in sorted(mission.goals, key=lambda g: (g.priority, g.goal_id)):
        goal = state.goals.get(gdef.goal_id)
        if goal is None:
            continue
        if goal.lifecycle in _TERMINAL:
            continue
        if not gdef.required and goal.lifecycle == GoalLifecycle.UNSEEN:
            continue
        pairs.append((gdef, goal))
    return pairs


def next_askable_goal(state: EngineState) -> GoalDefinition | None:
    for gdef, goal in unresolved_required_goals(state):
        max_att = getattr(gdef, "max_attempts", None) or goal.max_attempts
        if goal.delivered_attempts >= int(max_att):
            # Exhausted attempts → skip terminal, continue
            if goal.lifecycle not in _TERMINAL:
                goal.lifecycle = GoalLifecycle.SKIPPED
            continue
        return gdef
    return None


def ask_mission_goal_plan(
    state: EngineState,
    gdef: GoalDefinition,
    *,
    acknowledge: str = "",
    prelude: str = "",
    obligation: str = "ask_mission_goal",
) -> ResponsePlan:
    runtime = state.ensure_goal(gdef.goal_id)
    if runtime.lifecycle in {
        GoalLifecycle.AVAILABLE,
        GoalLifecycle.UNSEEN,
    }:
        runtime.lifecycle = GoalLifecycle.ACTIVE
    text = gdef.prompt_hint or gdef.description or gdef.goal_id
    if prelude:
        text = f"{prelude.rstrip()} {text}"
    return ResponsePlan(
        obligation=obligation,
        action="speak",
        mandatory_question=text,
        acknowledge=acknowledge,
        intent="ask_mission_goal",
        slot=gdef.goal_id,
        marks_question=True,
    )


def resume_mission_goal_plan(state: EngineState, goal_id: str) -> ResponsePlan | None:
    mission = mission_catalog(state)
    gdef = definition_by_id(mission, goal_id)
    if gdef is None:
        return None
    goal = state.goals.get(goal_id)
    if goal is None or goal.lifecycle in _TERMINAL:
        return None
    return ask_mission_goal_plan(
        state,
        gdef,
        obligation="resume_mission_goal",
    )


def capture_mission_suspend(state: EngineState) -> SuspendedObligation | None:
    def _suspend_for(q) -> SuspendedObligation | None:
        if q is None:
            return None
        if not (q.goal_id or q.intent == "ask_mission_goal"):
            return None
        gid = q.goal_id or q.slot
        goal = state.goals.get(gid) if gid else None
        if goal is not None and goal.lifecycle in _TERMINAL:
            return None
        return SuspendedObligation(
            kind="goal_question",
            goal_id=gid,
            slot=gid,
            intent=q.intent or "ask_mission_goal",
            reason="interrupted",
            resume_policy="after_issue",
        )

    return _suspend_for(state.delivered_question) or _suspend_for(state.playing_question)


def household_help_plan(state: EngineState, *, acknowledge: str = "") -> ResponsePlan:
    state.pending_episode_attribute = "needs_help"
    ep = state.active_episode_id
    return ResponsePlan(
        obligation="continue_active_episode",
        action="speak",
        mandatory_question=_HOUSEHOLD_HELP,
        acknowledge=acknowledge,
        intent="episode_needs_help",
        slot=f"episode_{ep}_needs_help" if ep else "needs_help",
        marks_question=True,
        episode_id=ep,
    )


def final_open_plan(*, acknowledge: str = "") -> ResponsePlan:
    return ResponsePlan(
        obligation="important_to_share",
        action="speak",
        mandatory_question=_FINAL_OPEN,
        acknowledge=acknowledge,
        intent="mission_final_open",
        slot="mission_final_open",
        marks_question=True,
    )


def identity_answer() -> str:
    return _IDENTITY


def opening_custom_greeting(elder_display_name: str) -> str:
    return (
        f"Здравствуйте! Это Вера, голосовой помощник сервиса Амвера. "
        f"Звоню насчёт {elder_display_name}."
    )


def schedule_custom_mission(state: EngineState, turn_context) -> ResponsePlan | None:
    """Authoritative conversation scheduling for custom CallMission only."""
    from packages.dialogue_engine.conversation_policy import ConversationObligation

    if not is_custom_mission(state):
        return None

    turn = turn_context.turn

    # 1) repair
    if turn and turn.dialogue_act == "repair":
        dq = state.delivered_question
        text = (dq.text if dq else "") or "Повторите, пожалуйста."
        return ResponsePlan(
            obligation=ConversationObligation.REPAIR,
            action="speak",
            mandatory_question=text,
            intent="repair_repeat",
            slot=dq.slot if dq else None,
            marks_question=bool(dq),
        )

    # 2) control
    if turn and turn.control not in ("none", "", None):
        return ResponsePlan(
            obligation=ConversationObligation.CONTROL,
            action="control",
            control=turn.control,
        )

    # Disposition handled in apply; scheduler must not re-ask declined.

    # 3) user question without pending answer → answer + resume/next
    if turn and turn.user_question and not turn.answers_pending_question:
        suspend = capture_mission_suspend(state) or state.suspended_obligation
        if suspend:
            state.suspended_obligation = suspend
        nxt = None
        if state.suspended_obligation and state.suspended_obligation.goal_id:
            nxt = resume_mission_goal_plan(state, state.suspended_obligation.goal_id)
            state.suspended_obligation = None
        if nxt is None:
            gdef = next_askable_goal(state)
            if gdef:
                nxt = ask_mission_goal_plan(state, gdef)
        if nxt is not None:
            nxt.answer_user_question = identity_answer()
            nxt.marks_question = True
            return nxt
        return ResponsePlan(
            obligation=ConversationObligation.ANSWER_USER_QUESTION,
            action="speak",
            answer_user_question=identity_answer(),
            intent="answer_user_question",
            marks_question=False,
        )

    # 4) resume suspended goal after issue handling
    if state.suspended_obligation and state.suspended_obligation.kind == "goal_question":
        # If open non-health episode still needs needs_help, ask that first.
        if _open_other_episode_needs_help(state):
            ack = ""
            if turn and turn.issue_mentions:
                ack = "Понимаю."
            return household_help_plan(state, acknowledge=ack)
        gid = state.suspended_obligation.goal_id
        state.suspended_obligation = None
        if gid:
            plan = resume_mission_goal_plan(state, gid)
            if plan:
                return plan

    # 5) new / open other-kind issue → one household follow-up, suspend mission
    if turn and turn.issue_mentions:
        suspend = capture_mission_suspend(state)
        if suspend:
            state.suspended_obligation = suspend
        if _open_other_episode_needs_help(state):
            return household_help_plan(state, acknowledge="Понимаю.")

    if _open_other_episode_needs_help(state):
        return household_help_plan(state)

    # 6) answer + user question already applied goals → next goal with identity if needed
    if turn and turn.user_question and turn.answers_pending_question:
        gdef = next_askable_goal(state)
        if gdef:
            plan = ask_mission_goal_plan(state, gdef)
            plan.answer_user_question = identity_answer()
            return plan

    # 7) next unresolved mission goal
    gdef = next_askable_goal(state)
    if gdef:
        return ask_mission_goal_plan(state, gdef)

    # 8) final open / close
    if not state.important_to_share_asked:
        state.important_to_share_asked = True
        return final_open_plan()

    if turn and turn.issue_mentions:
        # new issue after final open
        return household_help_plan(state, acknowledge="Хорошо, поняла.")

    if state.important_to_share_asked:
        state.important_to_share_resolved = True
        return ResponsePlan(
            obligation=ConversationObligation.SUMMARY_CLOSE,
            action="close_summary",
            close_reason="complete",
            marks_question=False,
        )

    return ResponsePlan(action="none")


def _open_other_episode_needs_help(state: EngineState) -> bool:
    for ep in state.issue_episodes.values():
        if ep.status == "resolved":
            continue
        if ep.kind != "other":
            continue
        if ep.known_attributes.get("needs_help"):
            continue
        if state.pending_episode_attribute == "needs_help" and state.active_episode_id == ep.episode_id:
            return True
        if not ep.known_attributes.get("needs_help"):
            state.active_episode_id = ep.episode_id
            return True
    return False
