"""Single mandatory action class per turn — fixed precedence, no mutual preempt deadlock."""

from __future__ import annotations

from enum import StrEnum

from packages.dialogue_engine.action_policy.actions import ActionKind, CandidateAction
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView


class MandatoryClass(StrEnum):
    SAFETY = "SAFETY"
    TERMINAL_CONTROL = "TERMINAL_CONTROL"
    REPAIR = "REPAIR"
    ANSWER_USER = "ANSWER_USER"
    ITS_META = "ITS_META"
    CLARIFY = "CLARIFY"
    CONVERSATION = "CONVERSATION"
    BACKGROUND_GOAL = "BACKGROUND_GOAL"
    SUMMARY_CLOSE = "SUMMARY_CLOSE"
    ACK_ONLY = "ACK_ONLY"


def _has_nonterminal_control(ctx: TurnContextView) -> bool:
    return ctx.control not in {"", "none", "stop_call"}


def _urgent_risk(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    return ctx.urgent_risk or snapshot.risk_level == "urgent"


def _unresolved_concern(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    if ctx.has_new_speaker_issue or snapshot.interrogatable_episodes:
        return False
    return ctx.unresolved_concern or (ctx.needs_clarification and not ctx.has_grounded_information)


def thread_context_eligible(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    """Only a grounded personal concern may defer nonurgent background collection.

    This does not reopen deferred optional clinical work, consume an obligation,
    or assign facts. Safety/control/clinical pending needs keep their owners.
    """
    return bool(
        snapshot.thread_active
        and snapshot.thread_statement.strip()
        and snapshot.thread_utterance_id
        and (ctx.utterance_id or not ctx.raw_text.strip())
        and (not ctx.utterance_id or ctx.utterance_id == snapshot.thread_utterance_id)
        and (snapshot.thread_willing or snapshot.thread_finished)
        and not snapshot.call_closed
        and not _urgent_risk(snapshot, ctx)
        and ctx.control in {"", "none"}
        and not ctx.repair
        and not ctx.user_question
        and not ctx.meta
        and not ctx.needs_clarification
        and not ctx.clarify_target
        and not ctx.unresolved_concern
        and not ctx.vague_negative_wellness
        and not ctx.has_new_speaker_issue
        and not snapshot.pending_episode_attribute
        and not snapshot.its_pending
        and not snapshot.probe_phase
        and not snapshot.outstanding_pending_obligation()
        and not snapshot.has_askable_open_issues(ctx)
    )


def _conversation_eligible(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    if snapshot.wellness_entry_covered:
        return True
    return bool(snapshot.interrogatable_episodes or ctx.has_new_speaker_issue)


def _background_eligible(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    if snapshot.has_askable_open_issues(ctx) or snapshot.its_pending:
        return False
    for goal in ("wellness", "mood", "sleep", "plans"):
        required = snapshot.mandatory_background_goals or goal in snapshot.required_background_goals
        if required and snapshot.background_status(goal) in {"unseen", "asked"}:
            return True
    return False


def _summary_close_eligible(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    if snapshot.has_askable_open_issues(ctx):
        return False
    if ctx.has_new_speaker_issue and not snapshot.transition_preferred(ctx):
        return False
    if not snapshot.important_to_share_resolved:
        return False
    if ctx.meta or ctx.unclear_without_grounding or _unresolved_concern(snapshot, ctx):
        return False
    return True


def compute_mandatory_class(snapshot: PolicySnapshot, ctx: TurnContextView) -> MandatoryClass:
    """Fixed precedence ending in scorer-driven CONVERSATION, not hard must-ask."""
    if _urgent_risk(snapshot, ctx):
        return MandatoryClass.SAFETY
    if ctx.explicit_farewell or _has_nonterminal_control(ctx):
        return MandatoryClass.TERMINAL_CONTROL
    if ctx.repair:
        return MandatoryClass.REPAIR
    if ctx.user_question:
        return MandatoryClass.ANSWER_USER
    if (ctx.meta and not ctx.has_grounded_information) or (
        snapshot.its_pending and ctx.unclear_without_grounding
    ):
        return MandatoryClass.ITS_META
    if _unresolved_concern(snapshot, ctx):
        return MandatoryClass.CLARIFY
    if (
        ctx.clarify_target
        and not ctx.has_new_speaker_issue
        and not snapshot.interrogatable_episodes
    ):
        return MandatoryClass.CLARIFY
    if thread_context_eligible(snapshot, ctx):
        if not snapshot.thread_finished or snapshot.thread_resume_slot:
            return MandatoryClass.CONVERSATION
    if _background_eligible(snapshot, ctx):
        return MandatoryClass.BACKGROUND_GOAL
    if _summary_close_eligible(snapshot, ctx):
        return MandatoryClass.SUMMARY_CLOSE
    if _conversation_eligible(snapshot, ctx):
        return MandatoryClass.CONVERSATION
    return MandatoryClass.ACK_ONLY


def action_matches_mandatory_class(
    action: CandidateAction,
    mandatory_class: MandatoryClass,
    snapshot: PolicySnapshot,
    ctx: TurnContextView,
) -> bool:
    kind = action.kind
    if mandatory_class == MandatoryClass.SAFETY:
        return kind == ActionKind.SAFETY
    if mandatory_class == MandatoryClass.TERMINAL_CONTROL:
        if ctx.explicit_farewell:
            return kind == ActionKind.GOODBYE_FINAL
        return kind == ActionKind.CONTROL
    if mandatory_class == MandatoryClass.REPAIR:
        return kind == ActionKind.REPAIR
    if mandatory_class == MandatoryClass.ANSWER_USER:
        return kind == ActionKind.ANSWER_USER
    if mandatory_class == MandatoryClass.ITS_META:
        return kind == ActionKind.LISTEN_META
    if mandatory_class == MandatoryClass.CLARIFY:
        return kind == ActionKind.CLARIFY
    if mandatory_class == MandatoryClass.CONVERSATION:
        if thread_context_eligible(snapshot, ctx) and (
            not snapshot.thread_finished or snapshot.thread_resume_slot
        ):
            # The existing legal set owns the personal move; medical candidates
            # cannot steal this scoped concern via their unrelated scores.
            return action.thread_mode is not None and kind in {
                ActionKind.ACK_ONLY,
                ActionKind.FOLLOW_USER_THREAD,
                ActionKind.BACKGROUND_GOAL,
            }
        return kind in {
            ActionKind.ASK_EPISODE,
            ActionKind.IMPORTANT_TO_SHARE,
            ActionKind.ACK_ONLY,
        }
    if mandatory_class == MandatoryClass.BACKGROUND_GOAL:
        return kind == ActionKind.BACKGROUND_GOAL
    if mandatory_class == MandatoryClass.SUMMARY_CLOSE:
        return kind == ActionKind.SUMMARY_CLOSE
    if mandatory_class == MandatoryClass.ACK_ONLY:
        return kind == ActionKind.ACK_ONLY
    return False
