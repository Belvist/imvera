"""Conversation policy — obligations inside DialogueEngine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from packages.dialogue_engine import questions
from packages.dialogue_engine.evidence_invariant import question_references_forbidden_site
from packages.dialogue_engine.issue_memory import (
    activate_next_pending_episode,
    episode_complete,
    get_active_episode,
)
from packages.dialogue_engine.state import EngineState, SuspendedObligation
from packages.dialogue_engine.turn_understanding import RichUserTurn


class ConversationObligation(StrEnum):
    SAFETY = "safety"
    CONTROL = "control"
    ANSWER_USER_QUESTION = "answer_user_question"
    HANDLE_CORRECTION = "handle_correction"
    ACKNOWLEDGE_IMPORTANT_FACT = "acknowledge_important_fact"
    CONTINUE_ACTIVE_EPISODE = "continue_active_episode"
    RESUME_PENDING_EPISODE = "resume_pending_episode"
    RESUME_SUSPENDED = "resume_suspended"
    BACKGROUND_GOAL = "background_goal"
    NEVER_SILENT = "never_silent"


@dataclass(frozen=True)
class PolicyDecision:
    obligation: ConversationObligation
    text: str = ""
    intent: str = ""
    slot: str | None = None
    marks_question: bool = False
    suspend: SuspendedObligation | None = None
    control: str | None = None


_IDENTITY_ANSWER = (
    "Я Вера, голосовой помощник IMVERA. Звоню, чтобы узнать, как вы себя чувствуете."
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


def _missing_attribute(state: EngineState, ep) -> str | None:
    from packages.dialogue_engine.semantic_kernel.information_gain import best_attribute_to_ask

    return best_attribute_to_ask(state, ep)


def _attribute_question(ep, attribute: str) -> tuple[str, str]:
    label = ep.primary_label.lower()
    if attribute == "duration":
        if "голов" in label:
            return "Как давно это продолжается?", "episode_headache_duration"
        return "Как давно это продолжается?", f"episode_{ep.episode_id}_duration"
    if attribute == "onset":
        if "голов" in label:
            return "Как давно болит голова?", "episode_headache_onset"
        return f"Как давно {ep.primary_label}?", f"episode_{ep.episode_id}_onset"
    if attribute == "severity":
        return "Боль сильная или терпимая?", "episode_headache_severity"
    if attribute == "current":
        return (
            f"Я уточняю про сейчас: {ep.primary_label} ещё беспокоит или уже прошло?",
            "episode_current_status",
        )
    return "Расскажите, пожалуйста, чуть подробнее.", "episode_followup"


def _correction_response(state: EngineState, turn: RichUserTurn) -> PolicyDecision:
    ep = get_active_episode(state)
    if ep is None and turn.issue_mentions:
        from packages.dialogue_engine.issue_memory import _find_episode_for_mention

        ep_id = _find_episode_for_mention(state, turn.issue_mentions[0])
        if ep_id:
            state.active_episode_id = ep_id
            ep = state.issue_episodes[ep_id]
    label = ep.primary_label if ep else "это"
    ack = f"Да, вы говорили, что {label}." if ep else "Понимаю."
    attribute = state.pending_episode_attribute or (ep and _missing_attribute(state, ep))
    if ep and attribute:
        state.pending_episode_attribute = attribute
        q_text, intent = _attribute_question(ep, attribute)
        if question_references_forbidden_site(state, q_text):
            q_text = (
                f"Я уточняю про сейчас: {ep.primary_label} ещё беспокоит или уже прошло?"
                if attribute == "current"
                else f"Расскажите про {ep.primary_label} чуть подробнее, пожалуйста."
            )
        return PolicyDecision(
            obligation=ConversationObligation.HANDLE_CORRECTION,
            text=f"{ack} {q_text}",
            intent=intent,
            slot=intent,
            marks_question=True,
        )
    return PolicyDecision(
        obligation=ConversationObligation.HANDLE_CORRECTION,
        text=f"{ack} Расскажите, пожалуйста, чуть подробнее.",
        intent="episode_correction_ack",
        marks_question=True,
    )


def _next_episode_question(state: EngineState) -> PolicyDecision | None:
    ep = get_active_episode(state)
    if ep is None:
        ep = activate_next_pending_episode(state)
    if ep is None:
        return None
    if episode_complete(ep):
        activate_next_pending_episode(state)
        ep = get_active_episode(state)
        if ep is None:
            return None

    attribute = _missing_attribute(state, ep)
    if attribute is None:
        ep.status = "resolved"
        activate_next_pending_episode(state)
        return _next_episode_question(state)

    state.pending_episode_attribute = attribute
    text, intent = _attribute_question(ep, attribute)
    if question_references_forbidden_site(state, text):
        return None
    return PolicyDecision(
        obligation=ConversationObligation.CONTINUE_ACTIVE_EPISODE,
        text=text,
        intent=intent,
        slot=intent,
        marks_question=True,
    )


def resume_episode_obligation(state: EngineState) -> PolicyDecision | None:
    """Resume generic IssueEpisode flow after topic slots complete."""
    if not state.active_episode_id and state.pending_episode_ids:
        activate_next_pending_episode(state)
    if not state.active_episode_id and not state.pending_episode_ids:
        return None
    return _next_episode_question(state)


def decide_conversation_policy(
    state: EngineState,
    turn: RichUserTurn,
) -> PolicyDecision | None:
    if turn.dialogue_act == "repair":
        from packages.dialogue_engine.question_context import repair_question_text

        slot = state.answer_context_slot() or "wellness"
        repair_text = repair_question_text(state, slot)
        return PolicyDecision(
            obligation=ConversationObligation.NEVER_SILENT,
            text=questions.repair_response(repair_text),
            intent="repair_repeat",
            slot=slot,
            marks_question=False,
        )

    if turn.control not in ("none", ""):
        return PolicyDecision(
            obligation=ConversationObligation.CONTROL,
            control=turn.control,
        )

    if turn.user_question and not turn.answers_pending_question:
        suspend = capture_suspended_obligation(state)
        return PolicyDecision(
            obligation=ConversationObligation.ANSWER_USER_QUESTION,
            text=_IDENTITY_ANSWER,
            intent="answer_user_question",
            marks_question=False,
            suspend=suspend,
        )

    if turn.correction:
        return _correction_response(state, turn)

    if state.suspended_obligation and not turn.user_question:
        suspended = state.suspended_obligation
        state.suspended_obligation = None
        if suspended.kind == "episode_question" and suspended.episode_id:
            state.active_episode_id = suspended.episode_id
            state.pending_episode_attribute = suspended.attribute
        resumed = _next_episode_question(state)
        if resumed:
            return PolicyDecision(
                obligation=ConversationObligation.RESUME_SUSPENDED,
                text=resumed.text,
                intent=resumed.intent,
                slot=resumed.slot,
                marks_question=resumed.marks_question,
            )

    if turn.issue_mentions:
        ack = _ack_for_mentions(turn)
        next_q = _next_episode_question(state)
        if next_q:
            text = f"{ack} {next_q.text}".strip() if ack else next_q.text
            return PolicyDecision(
                obligation=ConversationObligation.ACKNOWLEDGE_IMPORTANT_FACT,
                text=text,
                intent=next_q.intent,
                slot=next_q.slot,
                marks_question=next_q.marks_question,
            )

    if state.active_episode_id or state.pending_episode_ids:
        next_q = _next_episode_question(state)
        if next_q:
            return next_q

    if turn.dialogue_act == "backchannel":
        return None

    return None


def _ack_for_mentions(turn: RichUserTurn) -> str:
    if not turn.issue_mentions:
        return "Понимаю."
    primary = next(
        (m for m in turn.issue_mentions if m.role in ("primary", "independent", "unknown")),
        turn.issue_mentions[0],
    )
    return f"Понимаю, {primary.label}."
