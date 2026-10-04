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
    plan = ask_mission_goal_plan(
        state,
        gdef,
        obligation="resume_mission_goal",
    )
    plan.acknowledgement_kind = "resume_mission"
    return plan


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
    # Commit pending_episode_attribute only after delivery.
    state.pending_episode_attribute_planned = "needs_help"
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


def _grounded_answer_recall(question_words: frozenset[str], state: EngineState) -> str | None:
    """Quote accepted current-call evidence; never use unproven prior metadata."""
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.discourse import _FACT_THREAD_LABELS
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_text

    neutral = {"как", "какой", "что", "вы", "ты", "я", "мой", "у", "в", "про",
               "об", "о", "на", "сегодня", "сейчас", "человек", "себя", "дело"}
    quotes = []
    matched_goal = False
    for definition in state.mission_catalog:
        gid = definition.goal_id
        label = _FACT_THREAD_LABELS.get(gid, "")
        anchors = frozenset(normalize_text(" ".join((
            label, definition.prompt_hint, definition.description,
            *definition.aliases, *definition.semantic_hints,
        ))).split()) - neutral
        if not anchors.intersection(question_words):
            continue
        matched_goal = True
        record = state.slot_records.get(gid)
        if (
            state.slots.get(gid) == SlotStatus.FILLED and record is not None
            and record.source_turn_id and record.source_text.strip()
        ):
            quotes.append(record.source_text.strip())
        for observation in state.observations.values():
            if (
                getattr(observation, "goal_id", None) == gid
                and getattr(observation, "status", None) == "confirmed"
                and str(getattr(observation, "subject", "")) == "speaker"
                and getattr(observation, "source_turn_id", "")
                and getattr(observation, "evidence", "")
            ):
                quotes.append(observation.evidence.strip())
    unique = list(dict.fromkeys(quote for quote in quotes if len(quote) <= 300))
    if not matched_goal:
        from packages.dialogue_engine.discourse import recall_personal_statement

        quote = recall_personal_statement(state, question_words)
        if quote:
            return f"В этом разговоре вы сказали: «{quote}»."
    if len(unique) != 1:
        return None
    return f"В этом разговоре вы сказали: «{unique[0]}»."


def is_conversation_navigation(question: str) -> bool:
    """A request for the next conversational move, never a world prediction.

    Closed grammatical roles exclude entities, symptoms and actions such as
    medication. This is call navigation, not a general open-question classifier.
    """
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_text

    words = frozenset(normalize_text(question or "").split())
    return bool(
        "что" in words and words & {"далёкий", "дальше", "теперь"}
        and words <= {
            "а", "и", "ну", "что", "далёкий", "дальше", "теперь", "быть",
            "мы", "вы", "я", "делать", "ещё", "то",
        }
    )


def answer_user_question_text(question: str, *, state: EngineState | None = None) -> str:
    """Bounded service answers or evidenced recall, with explicit abstention.

    This existing answer owner is shared by daily, custom and policy paths.
    Morphological roles scope the answer: 'когда' alone cannot become a call
    schedule, and 'почему' alone cannot become a statement of service purpose.
    No model, fact write, personal preference or medical advice is produced.
    """
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_text

    words = frozenset(normalize_text(question or "").split())
    if is_conversation_navigation(question):
        return "Можем продолжить. Я уточню то, чего вы ещё не рассказали."
    addressee = bool(words & {"ты", "вы", "вера", "помощник"})
    identity_request = "кто" in words and not words & {"знать", "помнить", "я"}
    if addressee and (identity_request or words & {"робот", "человек"}):
        return _IDENTITY
    if addressee and words & {"любить", "нравиться", "предпочитать"}:
        return "У меня нет личных предпочтений. Но я могу выслушать ваш рассказ."
    recall = bool(words & {
        "говорить", "рассказывать", "рассказать", "сказать", "сообщать", "помнить",
    })
    if recall and words & {"что", "помнить"} and "я" in words:
        # Current-call evidence cannot answer a request about another day/call.
        earlier_context = bool(words & {"вчера", "раньше", "прошлый", "предыдущий"})
        answer = (_grounded_answer_recall(words, state)
                  if state is not None and not earlier_context else None)
        return answer or "В этом разговоре у меня нет подтверждённого ответа об этом."
    service_question = not words & {"знать", "помнить"} and (
        addressee or words & {"сервис", "амвера", "звонок", "опрос"}
    )
    if service_question and words & {"когда", "ещё", "еще", "снова", "следующий"} and (
        words & {"позвонить", "звонить", "звонок"}
    ):
        return "О следующих звонках решает семья в приложении Амвера. Точного времени у меня нет."
    if words & {"ответ", "информация", "данные", "разговор", "запись"} and (
        words & {
            "увидеть", "видеть", "передать", "сохранять", "записать",
            "получить", "слушать", "доступ",
        }
    ):
        return (
            "Ответы используются в сервисе Амвера для информирования близких. "
            "Доступ зависит от настроек и согласия."
        )
    purpose = "зачем" in words or "почему" in words or {"для", "что"} <= words
    if purpose and service_question and words & {"звонить", "позвонить", "спрашивать", "опрос"}:
        if state is not None and is_custom_mission(state):
            return "Это звонок по поручению в сервисе Амвера. Вы можете не отвечать на вопросы."
        return (
            "Звоню из сервиса Амвера, чтобы узнать, как у вас дела. "
            "Вы можете не отвечать на вопросы."
        )
    if addressee and "спрашивать" in words and words & {"что", "какой"}:
        delivered = state.delivered_question if state is not None else None
        if delivered is not None and delivered.text.strip():
            return f"Я спрашивала: «{delivered.text.strip()}»."
    if words & {"мочь", "уметь"} and (
        (addressee and "что" in words)
        or words & {"разговаривать", "поговорить", "слушать", "общаться"}
    ):
        return "Могу выслушать вас, уточнить важное и записать то, что вы сообщите."
    return "На этот вопрос у меня нет надёжного ответа."


def identity_answer() -> str:
    return _IDENTITY


def opening_custom_greeting(elder_display_name: str) -> str:
    return (
        f"Здравствуйте, {elder_display_name}! "
        "Это Вера, голосовой помощник сервиса Амвера."
    )


def schedule_custom_mission(state: EngineState, turn_context) -> ResponsePlan | None:
    """Authoritative conversation scheduling for custom CallMission only."""
    from packages.dialogue_engine.conversation_policy import ConversationObligation

    if not is_custom_mission(state):
        return None

    turn = turn_context.turn

    # 0) SAFETY always first — RED → one clarification → user answer → close.
    # Never resume mission goals after RED.
    if state.safety_mode == "red" or state.risk_handling:
        user_answer = bool(turn and (getattr(turn, "raw_text", "") or "").strip())
        if state.safety_clarify_count >= 2 or (
            state.safety_clarify_count >= 1 and user_answer
        ):
            state.call_closed = True
            state.closing_reason = "safety_red"
            state.suspended_obligation = None
            state.pending_resume_goal_id = None
            return ResponsePlan(
                obligation=ConversationObligation.SUMMARY_CLOSE,
                action="speak",
                mandatory_question="Поняла. Завершаю звонок.",
                intent="safety_close",
                close_reason="safety_red",
                marks_question=False,
            )
        # Clarification spoken / waiting for user — do not resume mission.
        return ResponsePlan(action="none")

    # 0b) third-party / target presence
    if state.target_presence == "third_party":
        name = state.target_display_name or state.elder_display_name
        return ResponsePlan(
            obligation="target_presence",
            action="speak",
            mandatory_question=f"Могу я поговорить с {name}?",
            intent="ask_target_person",
            slot="target_presence",
            marks_question=True,
        )
    if state.target_presence == "unavailable":
        state.call_closed = True
        state.closing_reason = "no_answer"
        return ResponsePlan(
            obligation=ConversationObligation.SUMMARY_CLOSE,
            action="close_summary",
            close_reason="no_answer",
            marks_question=False,
        )

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
        if turn.control == "wrong_person":
            state.target_presence = "third_party"
            name = state.target_display_name or state.elder_display_name
            return ResponsePlan(
                obligation="target_presence",
                action="speak",
                mandatory_question=f"Могу я поговорить с {name}?",
                intent="ask_target_person",
                slot="target_presence",
                marks_question=True,
            )
        return ResponsePlan(
            obligation=ConversationObligation.CONTROL,
            action="control",
            control=turn.control,
        )

    ans_user = ""
    if turn and turn.user_question:
        ans_user = answer_user_question_text(turn.user_question, state=state)

    # 3) user question without pending answer → answer + resume/next
    if turn and turn.user_question and not turn.answers_pending_question:
        suspend = capture_mission_suspend(state) or state.suspended_obligation
        if suspend:
            state.suspended_obligation = suspend
        nxt = None
        if state.suspended_obligation and state.suspended_obligation.goal_id:
            gid = state.suspended_obligation.goal_id
            state.pending_resume_goal_id = gid
            nxt = resume_mission_goal_plan(state, gid)
            # Do not clear suspended until delivery.
        if nxt is None:
            gdef = next_askable_goal(state)
            if gdef:
                nxt = ask_mission_goal_plan(state, gdef)
        if nxt is not None:
            nxt.answer_user_question = ans_user or identity_answer()
            nxt.marks_question = True
            return nxt
        return ResponsePlan(
            obligation=ConversationObligation.ANSWER_USER_QUESTION,
            action="speak",
            answer_user_question=ans_user or identity_answer(),
            intent="answer_user_question",
            marks_question=False,
        )

    # 3b) Health interrupts any mission, using the SAME episode planner as
    # daily check. Previously only household issues suspended custom goals,
    # so a complaint was recorded while Vera repeated an unrelated question.
    if any(
        ep.kind != "other" and ep.status != "resolved" and ep.subject != "other_person"
        for ep in state.issue_episodes.values()
    ):
        from packages.dialogue_engine.conversation_policy import (
            _grounded_ack_for_mentions,
            _next_episode_plan,
        )

        suspend = capture_mission_suspend(state)
        if suspend is not None:
            state.suspended_obligation = suspend
        episode_plan = _next_episode_plan(state)
        if episode_plan is not None:
            if turn and turn.issue_mentions and not episode_plan.acknowledge:
                episode_plan.acknowledge = _grounded_ack_for_mentions(turn)
            return episode_plan

    # 4) resume suspended goal after issue handling
    if state.suspended_obligation and state.suspended_obligation.kind == "goal_question":
        if _open_other_episode_needs_help(state):
            ack = "Понимаю." if turn and turn.issue_mentions else ""
            return household_help_plan(state, acknowledge=ack)
        gid = state.suspended_obligation.goal_id
        if gid:
            state.pending_resume_goal_id = gid
            plan = resume_mission_goal_plan(state, gid)
            if plan:
                if turn and turn.issue_mentions:
                    from packages.dialogue_engine.conversation_policy import (
                        _grounded_ack_for_mentions,
                    )

                    plan.acknowledge = _grounded_ack_for_mentions(turn)
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

    # 6) answer + user question → next goal with bounded answer
    if turn and turn.user_question and turn.answers_pending_question:
        gdef = next_askable_goal(state)
        if gdef:
            plan = ask_mission_goal_plan(state, gdef)
            plan.answer_user_question = ans_user or identity_answer()
            return plan

    # 7) next unresolved mission goal
    gdef = next_askable_goal(state)
    if gdef:
        ack = ""
        if turn and turn.issue_mentions:
            from packages.dialogue_engine.conversation_policy import _grounded_ack_for_mentions

            ack = _grounded_ack_for_mentions(turn)
        return ask_mission_goal_plan(state, gdef, acknowledge=ack)

    # 8) final open / close — asked flag committed only after delivery
    if not state.important_to_share_asked and not state.important_to_share_planned:
        state.important_to_share_planned = True
        return final_open_plan()

    if turn and turn.issue_mentions and state.important_to_share_asked:
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
        if (
            state.pending_episode_attribute == "needs_help"
            and state.active_episode_id == ep.episode_id
        ):
            return True
        if state.pending_episode_attribute_planned == "needs_help":
            return False  # already proposed, waiting delivery
        if not ep.known_attributes.get("needs_help"):
            state.active_episode_id = ep.episode_id
            return True
    return False
