"""Conversation policy — single scheduler for next-turn decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine import questions
from packages.dialogue_engine.evidence_invariant import question_references_forbidden_site
from packages.dialogue_engine.issue_memory import (
    activate_next_pending_episode,
    episode_complete,
    get_active_episode,
)
from packages.dialogue_engine.question_context import QuestionNeed
from packages.dialogue_engine.response_plan import ResponsePlan
from packages.dialogue_engine.state import (
    BackgroundGoalCoverage,
    CheckPath,
    EngineState,
    SuspendedObligation,
)
from packages.dialogue_engine.turn_understanding import RichUserTurn


class ConversationObligation(StrEnum):
    SAFETY = "safety"
    CONTROL = "control"
    REPAIR = "repair"
    ANSWER_USER_QUESTION = "answer_user_question"
    HANDLE_CORRECTION = "handle_correction"
    ACKNOWLEDGE_IMPORTANT_FACT = "acknowledge_important_fact"
    CONTINUE_ACTIVE_EPISODE = "continue_active_episode"
    RESUME_PENDING_EPISODE = "resume_pending_episode"
    RESUME_SUSPENDED = "resume_suspended"
    IMPORTANT_TO_SHARE = "important_to_share"
    BACKGROUND_GOAL = "background_goal"
    SUMMARY_CLOSE = "summary_close"
    NEVER_SILENT = "never_silent"


@dataclass(frozen=True)
class TurnContext:
    turn: RichUserTurn | None = None
    newly_filled_slots: tuple[str, ...] = ()
    user_text: str = ""
    answer_slot: str | None = None
    clarify: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    """Legacy adapter — prefer ResponsePlan from schedule_next_action."""

    obligation: ConversationObligation
    text: str = ""
    intent: str = ""
    slot: str | None = None
    marks_question: bool = False
    suspend: SuspendedObligation | None = None
    control: str | None = None


_IDENTITY_ANSWER = (
    "Я Вера, голосовой помощник сервиса Амвера. "
    "Звоню, чтобы узнать, как вы себя чувствуете."
)
_IMPORTANT_TO_SHARE_QUESTION = questions.important_to_share_question()


def _is_important_to_share_decline(text: str) -> bool:
    """Soft «nothing more» answers to the closing add-anything question."""
    import re

    low = text.lower().strip().rstrip(".!?")
    if not low:
        return False
    if low in (
        "нет",
        "неа",
        "ничего",
        "не",
        "всё",
        "все",
        "нет ничего",
        "пока всё",
        "пока все",
    ):
        return True
    strong = (
        "нечего добавить",
        "не хочу добавить",
        "ничего добавить",
        "сказал уже",
        "сказала уже",
        "я ж сказал",
        "я же сказал",
        "я уже сказал",
        "на этом всё",
        "на этом все",
        "больше нечего",
        "уже всё сказал",
        "уже все сказал",
    )
    if any(m in low for m in strong):
        return True
    # «больше ничего» is decline only when not a meta question about Vera asking more.
    if "больше ничего" in low and not any(
        x in low for x in ("спроси", "хотите", "слушаете", "это всё?", "это все?")
    ):
        return True
    soft_no = (
        "вроде бы нет",
        "вроде нет",
        "да нет",
        "да вроде нет",
        "ничего такого",
        "уже всё",
        "уже все",
    )
    if any(m in low for m in soft_no):
        return True
    if re.search(r"\bнет\b", low) and any(
        x in low for x in ("вроде", "больше", "ничего", "толком")
    ):
        return True
    if re.search(r"^(так\s+)?вроде\s+(бы\s+)?вс[её](\s+нормально)?\.?$", low):
        return True
    return False


def _record_important_share(state: EngineState, text: str) -> None:
    note = text.strip()
    if not note:
        return
    state.observations["important_to_share"] = note


def _classify_important_to_share_answer(
    turn: RichUserTurn | None,
    raw: str,
) -> str:
    """Semantic class for ITS answers — raw text alone is never a recorded fact."""
    if _is_important_to_share_decline(raw):
        return "DECLINE"
    if turn is not None:
        if turn.control not in ("none", ""):
            return "CONTROL"
        if turn.dialogue_act == "repair":
            return "REPAIR"
        if turn.user_question:
            return "USER_QUESTION_OR_META"
        if turn.issue_mentions or turn.goal_facts or turn.correction:
            return "NEW_GROUNDED_INFORMATION"
        if turn.dialogue_act in ("unclear", "backchannel"):
            return "UNCLEAR"
    # Meaningful text without grounded extraction → not a share note.
    return "UNCLEAR"


_ITS_META_LISTEN = (
    "Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно."
)


def capture_suspended_obligation(state: EngineState) -> SuspendedObligation | None:
    ep = get_active_episode(state)
    if ep and state.pending_episode_attribute:
        return SuspendedObligation(
            kind="episode_question",
            episode_id=ep.episode_id,
            attribute=state.pending_episode_attribute,
            slot=f"episode_{ep.episode_id}_{state.pending_episode_attribute}",
            intent=f"episode_{ep.episode_id}_{state.pending_episode_attribute}",
        )
    if state.delivered_question:
        return SuspendedObligation(
            kind="slot_question",
            slot=state.delivered_question.slot,
            intent=state.delivered_question.intent,
        )
    return None


def episode_question_for_attribute(ep, attribute: str) -> tuple[str, str]:
    label = ep.primary_label.lower()
    if attribute == "duration":
        if "голов" in label:
            return "Как давно болит голова?", "episode_headache_duration"
        return "Как давно это продолжается?", f"episode_{ep.episode_id}_duration"
    if attribute == "onset":
        if "голов" in label:
            return "Как давно болит голова?", "episode_headache_onset"
        return f"Как давно {ep.primary_label}?", f"episode_{ep.episode_id}_onset"
    if attribute == "severity":
        if "голов" in label:
            return "Боль сильная или терпимая?", "episode_headache_severity"
        return (
            f"Насколько сильно {ep.primary_label}?",
            f"episode_{ep.episode_id}_severity",
        )
    if attribute == "current":
        return (
            f"Я уточняю про сейчас: {ep.primary_label} ещё беспокоит или уже прошло?",
            "episode_current_status",
        )
    if attribute == "concern":
        return questions.probe_question("concern"), "probe_concern"
    return "Расскажите, пожалуйста, чуть подробнее.", "episode_followup"


def _missing_question_need(state: EngineState, ep) -> QuestionNeed | None:
    from packages.dialogue_engine.semantic_kernel.information_gain import best_question_need

    return best_question_need(state, ep)


def _missing_attribute(state: EngineState, ep) -> str | None:
    need = _missing_question_need(state, ep)
    return need.attribute if need else None


def _all_episodes_resolved(state: EngineState) -> bool:
    if state.active_episode_id:
        ep = state.issue_episodes.get(state.active_episode_id)
        if ep and ep.status != "resolved":
            return False
    for eid in state.pending_episode_ids:
        ep = state.issue_episodes.get(eid)
        if ep and ep.status != "resolved":
            return False
    if state.issue_episodes:
        return all(ep.status == "resolved" for ep in state.issue_episodes.values())
    return True


def _has_open_episodes(state: EngineState) -> bool:
    if state.active_episode_id:
        ep = state.issue_episodes.get(state.active_episode_id)
        if ep and ep.status != "resolved":
            return True
    for eid in state.pending_episode_ids:
        ep = state.issue_episodes.get(eid)
        if ep and ep.status != "resolved":
            return True
    return False


def _mark_slot_coverage(state: EngineState, slot: str, coverage: BackgroundGoalCoverage) -> None:
    state.set_background_goal_coverage(slot, coverage)


def _sync_background_coverage_from_fills(state: EngineState, filled: tuple[str, ...]) -> None:
    for slot in filled:
        if slot in state.background_goal_status:
            _mark_slot_coverage(state, slot, BackgroundGoalCoverage.ANSWERED)


def _next_background_goal(state: EngineState) -> str | None:
    from packages.dialogue_engine.policy import can_ask_slot

    order = ("mood", "sleep", "plans")
    if state.slots.get("wellness") == SlotStatus.OPEN:
        order = ("wellness", "mood", "sleep", "plans")
    for slot in order:
        if not state.background_goal_needs_attention(slot):
            continue
        if not can_ask_slot(state, slot):
            _mark_slot_coverage(state, slot, BackgroundGoalCoverage.SKIPPED)
            continue
        return slot
    return None


def _episode_plan(state: EngineState, ep, need: QuestionNeed) -> ResponsePlan | None:
    state.pending_episode_attribute = need.attribute
    text, intent = episode_question_for_attribute(ep, need.attribute)
    if question_references_forbidden_site(state, text):
        return None
    return ResponsePlan(
        obligation=ConversationObligation.CONTINUE_ACTIVE_EPISODE,
        action="speak",
        episode_id=ep.episode_id,
        question_needs=[need],
        intent=intent,
        slot=intent,
        mandatory_question=text if not need.is_compound else "",
        marks_question=True,
    )


def _next_episode_plan(state: EngineState) -> ResponsePlan | None:
    ep = get_active_episode(state)
    if ep is None:
        ep = activate_next_pending_episode(state)
    if ep is None:
        return None
    if episode_complete(ep):
        from packages.dialogue_engine.issue_memory import finalize_episode_if_complete

        finalize_episode_if_complete(ep)
        activate_next_pending_episode(state)
        ep = get_active_episode(state)
        if ep is None:
            return None

    need = _missing_question_need(state, ep)
    if need is None:
        from packages.dialogue_engine.issue_memory import finalize_episode_if_complete

        finalize_episode_if_complete(ep)
        activate_next_pending_episode(state)
        return _next_episode_plan(state)

    return _episode_plan(state, ep, need)


def _wellness_entry_covered(state: EngineState) -> bool:
    if state.slots.get("wellness") != SlotStatus.OPEN:
        return True
    status = state.background_goal_status.get("wellness", BackgroundGoalCoverage.UNSEEN)
    if status in (
        BackgroundGoalCoverage.ANSWERED,
        BackgroundGoalCoverage.COVERED_FROM_SPEECH,
    ):
        return True
    # Mood/sleep already answered after opening also counts as entry coverage.
    for slot in ("mood", "sleep"):
        st = state.background_goal_status.get(slot, BackgroundGoalCoverage.UNSEEN)
        if st in (
            BackgroundGoalCoverage.ANSWERED,
            BackgroundGoalCoverage.COVERED_FROM_SPEECH,
        ):
            return True
        if state.slots.get(slot) == SlotStatus.FILLED:
            return True
    return False


def _important_to_share_plan(state: EngineState) -> ResponsePlan | None:
    if state.important_to_share_asked or state.important_to_share_resolved:
        return None
    if _has_open_episodes(state):
        return None
    if not _wellness_entry_covered(state):
        return None
    state.important_to_share_asked = True
    return ResponsePlan(
        obligation=ConversationObligation.IMPORTANT_TO_SHARE,
        action="speak",
        mandatory_question=_IMPORTANT_TO_SHARE_QUESTION,
        intent="important_to_share",
        slot="important_to_share",
        marks_question=True,
    )


def _probe_plan(state: EngineState, *, clarify: bool = False) -> ResponsePlan | None:
    if not state.probe_phase:
        return None
    # Issues own the turn — probe is compatibility context only.
    if _has_open_episodes(state):
        return None
    phase = state.probe_phase
    return ResponsePlan(
        obligation=ConversationObligation.CONTINUE_ACTIVE_EPISODE,
        action="speak",
        question_needs=[QuestionNeed.for_attribute(phase)],
        slot=f"probe_{phase}",
        intent=f"probe_{phase}",
        marks_question=True,
        clarification=clarify,
    )


def _topic_plan(state: EngineState) -> ResponsePlan | None:
    from packages.dialogue_engine.topic_tracker import next_topic_prompt, topic_slot

    prompt = next_topic_prompt(state)
    if prompt is None:
        return None
    return ResponsePlan(
        obligation=ConversationObligation.ACKNOWLEDGE_IMPORTANT_FACT,
        action="speak",
        intent=prompt.intent,
        slot=topic_slot(prompt.family),
        mandatory_question=questions.topic_question(prompt.intent),
        marks_question=True,
    )




def _background_goal_plan(
    state: EngineState,
    *,
    filled: tuple[str, ...] = (),
) -> ResponsePlan | None:
    slot = _next_background_goal(state)
    if slot is None:
        return None
    _mark_slot_coverage(state, slot, BackgroundGoalCoverage.ASKED)
    return ResponsePlan(
        obligation=ConversationObligation.BACKGROUND_GOAL,
        action="speak",
        acknowledge_facts=list(filled),
        next_slot=slot,
        intent=f"check_{slot}",
        slot=slot,
        marks_question=True,
    )


def _summary_plan(state: EngineState, *, acknowledge: str = "") -> ResponsePlan:
    return ResponsePlan(
        obligation=ConversationObligation.SUMMARY_CLOSE,
        action="close_summary",
        close_reason="complete",
        marks_question=False,
        acknowledge=acknowledge,
    )


def _correction_plan(state: EngineState, turn: RichUserTurn) -> ResponsePlan:
    ep = get_active_episode(state)
    if ep is None and turn.issue_mentions:
        from packages.dialogue_engine.issue_memory import _find_episode_for_mention

        ep_id = _find_episode_for_mention(state, turn.issue_mentions[0])
        if ep_id:
            state.active_episode_id = ep_id
            ep = state.issue_episodes[ep_id]
    label = ep.primary_label if ep else ""
    ack = f"Да, вы говорили, что {label}." if ep else "Понимаю."
    need = None
    if ep:
        pending = state.pending_episode_attribute
        need = (
            QuestionNeed.for_attribute(pending)
            if pending
            else _missing_question_need(state, ep)
        )
    if ep and need:
        q_plan = _episode_plan(state, ep, need)
        if q_plan:
            q_plan.obligation = ConversationObligation.HANDLE_CORRECTION
            q_plan.acknowledge = ack
            return q_plan
    return ResponsePlan(
        obligation=ConversationObligation.HANDLE_CORRECTION,
        action="speak",
        acknowledge=ack,
        mandatory_question="Расскажите, пожалуйста, чуть подробнее.",
        intent="episode_correction_ack",
        marks_question=True,
    )


def _grounded_ack_for_mentions(turn: RichUserTurn) -> str:
    if not turn.issue_mentions:
        return ""
    primary = next(
        (m for m in turn.issue_mentions if m.role in ("primary", "independent", "unknown")),
        turn.issue_mentions[0],
    )
    quote = primary.evidence.quote if primary.evidence and primary.evidence.quote else ""
    if quote and len(quote) > 3:
        return f"Понимаю, {quote.rstrip('.') }."
    return "Понимаю."


def schedule_next_action(state: EngineState, turn_context: TurnContext) -> ResponsePlan:
    """Canonical scheduler — all next-turn decisions flow through here."""
    turn = turn_context.turn
    filled = turn_context.newly_filled_slots
    clarify = turn_context.clarify
    _sync_background_coverage_from_fills(state, filled)

    if turn and turn.dialogue_act == "repair":
        from packages.dialogue_engine.question_context import repair_question_text

        slot = state.answer_context_slot() or "wellness"
        repair_text = repair_question_text(state, slot)
        return ResponsePlan(
            obligation=ConversationObligation.REPAIR,
            action="speak",
            mandatory_question=questions.repair_response(repair_text),
            intent="repair_repeat",
            slot=slot,
            marks_question=False,
        )

    if turn and turn.control not in ("none", ""):
        return ResponsePlan(
            obligation=ConversationObligation.CONTROL,
            action="control",
            control=turn.control,
        )

    if turn and turn.user_question and not turn.answers_pending_question:
        suspend = capture_suspended_obligation(state)
        return ResponsePlan(
            obligation=ConversationObligation.ANSWER_USER_QUESTION,
            action="speak",
            answer_user_question=_IDENTITY_ANSWER,
            intent="answer_user_question",
            marks_question=False,
            suspend=suspend,
        )

    if turn and turn.correction:
        return _correction_plan(state, turn)

    if state.suspended_obligation and turn and not turn.user_question:
        suspended = state.suspended_obligation
        state.suspended_obligation = None
        if suspended.kind == "episode_question" and suspended.episode_id:
            state.active_episode_id = suspended.episode_id
            state.pending_episode_attribute = suspended.attribute
        resumed = _next_episode_plan(state)
        if resumed:
            resumed.obligation = ConversationObligation.RESUME_SUSPENDED
            return resumed
        bg = _background_goal_plan(state, filled=filled)
        if bg:
            bg.obligation = ConversationObligation.RESUME_SUSPENDED
            return bg

    if turn and turn.issue_mentions:
        if state.important_to_share_asked and not state.important_to_share_resolved:
            state.important_to_share_resolved = True
        ack = _grounded_ack_for_mentions(turn)
        next_q = _next_episode_plan(state)
        if next_q:
            if ack:
                next_q.acknowledge = ack
            next_q.obligation = ConversationObligation.ACKNOWLEDGE_IMPORTANT_FACT
            return next_q

    if _has_open_episodes(state) and turn is not None:
        pending = state.pending_episode_attribute
        if pending in ("onset", "duration", "severity", "current"):
            from packages.dialogue_engine.issue_memory import (
                extract_grounded_onset_value,
                extract_grounded_severity_value,
            )

            grounded = False
            if pending in ("onset", "duration"):
                grounded = extract_grounded_onset_value(turn.raw_text) is not None
            elif pending == "severity":
                grounded = extract_grounded_severity_value(turn.raw_text) is not None
            else:
                grounded = bool(turn.issue_mentions) or turn.answers_pending_question
            if (
                not grounded
                and not turn.issue_mentions
                and _classify_important_to_share_answer(turn, turn.raw_text)
                in ("USER_QUESTION_OR_META", "UNCLEAR", "REPAIR")
            ):
                next_q = _next_episode_plan(state)
                if next_q:
                    next_q.acknowledge = "Я вас слушаю."
                    return next_q
                return ResponsePlan(
                    obligation=ConversationObligation.NEVER_SILENT,
                    action="speak",
                    mandatory_question=_ITS_META_LISTEN,
                    intent="listen_open",
                    marks_question=True,
                )

    if _has_open_episodes(state):
        from packages.dialogue_engine.policy import can_ask_slot

        next_q = _next_episode_plan(state)
        if next_q and next_q.slot and not can_ask_slot(state, next_q.slot):
            state.pending_episode_attribute = None
            next_q = None
        if next_q:
            return next_q

    if turn and turn.dialogue_act == "backchannel":
        return ResponsePlan(action="none")

    if state.check_path == CheckPath.URGENT:
        return ResponsePlan(
            obligation=ConversationObligation.SAFETY,
            action="close_urgent",
        )

    probe = _probe_plan(state, clarify=clarify)
    if probe:
        return probe

    topic = _topic_plan(state)
    if topic:
        return topic

    if state.important_to_share_asked and not state.important_to_share_resolved:
        raw = ""
        if turn and turn.raw_text.strip():
            raw = turn.raw_text.strip()
        elif turn_context.user_text.strip():
            raw = turn_context.user_text.strip()
        if not raw:
            return ResponsePlan(
                obligation=ConversationObligation.IMPORTANT_TO_SHARE,
                action="speak",
                mandatory_question=_IMPORTANT_TO_SHARE_QUESTION,
                intent="important_to_share",
                slot="important_to_share",
                marks_question=True,
            )
        its_class = _classify_important_to_share_answer(turn, raw)
        if its_class == "DECLINE":
            state.important_to_share_resolved = True
            if state.mandatory_background_goals:
                bg = _background_goal_plan(state, filled=filled)
                if bg:
                    return bg
            return _summary_plan(state)
        if its_class == "NEW_GROUNDED_INFORMATION":
            state.important_to_share_resolved = True
            if turn and turn.issue_mentions:
                next_q = _next_episode_plan(state)
                if next_q:
                    next_q.acknowledge = "Поняла."
                    return next_q
            _record_important_share(state, raw)
            if state.mandatory_background_goals:
                bg = _background_goal_plan(state, filled=filled)
                if bg:
                    return bg
            return _summary_plan(state, acknowledge="Хорошо, записала.")
        if its_class in ("USER_QUESTION_OR_META", "REPAIR", "UNCLEAR", "CONTROL"):
            # Do not resolve ITS — keep conversation open.
            return ResponsePlan(
                obligation=ConversationObligation.IMPORTANT_TO_SHARE,
                action="speak",
                mandatory_question=_ITS_META_LISTEN,
                intent="important_to_share_listen",
                slot="important_to_share",
                marks_question=True,
            )

    its = _important_to_share_plan(state)
    if its:
        return its

    bg = _background_goal_plan(state, filled=filled)
    if bg:
        return bg

    if not _has_open_episodes(state) or _all_episodes_resolved(state):
        if _next_background_goal(state) is None:
            if not state.important_to_share_resolved:
                if state.first_user_turn_received:
                    state.important_to_share_asked = True
                    return ResponsePlan(
                        obligation=ConversationObligation.IMPORTANT_TO_SHARE,
                        action="speak",
                        mandatory_question=_IMPORTANT_TO_SHARE_QUESTION,
                        intent="important_to_share",
                        slot="important_to_share",
                        marks_question=True,
                    )
            return _summary_plan(state)

    return ResponsePlan(
        obligation=ConversationObligation.NEVER_SILENT,
        action="speak",
        mandatory_question=questions.slot_question("wellness", state=state),
        intent="clarify_wellness",
        slot="wellness",
        marks_question=True,
    )


def resume_episode_obligation(state: EngineState) -> PolicyDecision | None:
    """Compatibility adapter for legacy call sites."""
    plan = _next_episode_plan(state)
    if plan is None:
        return None
    from packages.dialogue_engine.response_plan import composed_text, render_response_plan

    rendered = render_response_plan(plan, state)
    return PolicyDecision(
        obligation=ConversationObligation.CONTINUE_ACTIVE_EPISODE,
        text=composed_text(rendered),
        intent=rendered.intent,
        slot=rendered.slot,
        marks_question=rendered.marks_question,
    )


def decide_conversation_policy(
    state: EngineState,
    turn: RichUserTurn,
) -> PolicyDecision | None:
    """Legacy entry — delegates to schedule_next_action."""
    from packages.dialogue_engine.response_plan import composed_text, render_response_plan

    plan = schedule_next_action(
        state,
        TurnContext(turn=turn, user_text=turn.raw_text),
    )
    if plan.action == "none":
        return None
    if plan.action == "control":
        return PolicyDecision(
            obligation=ConversationObligation.CONTROL,
            control=plan.control,
        )
    rendered = render_response_plan(plan, state)
    text = composed_text(rendered)
    if not text and plan.obligation != ConversationObligation.CONTROL:
        return None
    return PolicyDecision(
        obligation=plan.obligation or ConversationObligation.NEVER_SILENT,
        text=text,
        intent=rendered.intent,
        slot=rendered.slot,
        marks_question=rendered.marks_question,
        suspend=plan.suspend if isinstance(plan.suspend, SuspendedObligation) else None,
        control=plan.control,
    )


# Backward compat for question_context import
_attribute_question = episode_question_for_attribute
