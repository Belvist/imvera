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
    ISSUE = "ISSUE"
    CLARIFY = "CLARIFY"
    IMPORTANT_TO_SHARE = "IMPORTANT_TO_SHARE"
    BACKGROUND_GOAL = "BACKGROUND_GOAL"
    SUMMARY_CLOSE = "SUMMARY_CLOSE"
    ACK_ONLY = "ACK_ONLY"


def _has_nonterminal_control(ctx: TurnContextView) -> bool:
    return ctx.control not in {"", "none", "stop_call"}


def _important_to_share_eligible(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    if snapshot.attention_episodes or ctx.has_new_issue:
        return False
    if not snapshot.wellness_entry_covered:
        return False
    if snapshot.important_to_share_asked or snapshot.important_to_share_resolved:
        return False
    return True


def _background_eligible(snapshot: PolicySnapshot) -> bool:
    if snapshot.attention_episodes or snapshot.its_pending:
        return False
    for goal in ("wellness", "mood", "sleep", "plans"):
        required = snapshot.mandatory_background_goals or goal in snapshot.required_background_goals
        if required and snapshot.background_status(goal) in {"unseen", "asked"}:
            return True
    return False


def _summary_close_eligible(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    if snapshot.attention_episodes or ctx.has_new_issue:
        return False
    if not snapshot.important_to_share_resolved:
        return False
    if ctx.meta or ctx.unclear_without_grounding:
        return False
    return True


def compute_mandatory_class(snapshot: PolicySnapshot, ctx: TurnContextView) -> MandatoryClass:
    """Fixed precedence: SAFETY → terminal/control → REPAIR → … → ACK_ONLY."""
    if snapshot.risk_level == "urgent":
        return MandatoryClass.SAFETY
    if ctx.explicit_farewell or _has_nonterminal_control(ctx):
        return MandatoryClass.TERMINAL_CONTROL
    if ctx.repair:
        return MandatoryClass.REPAIR
    if ctx.user_question:
        return MandatoryClass.ANSWER_USER
    if (
        (ctx.meta and not ctx.has_grounded_information)
        or (snapshot.its_pending and ctx.unclear_without_grounding)
    ):
        return MandatoryClass.ITS_META
    if snapshot.attention_episodes or ctx.has_new_issue:
        return MandatoryClass.ISSUE
    clarify_target = ctx.clarify_target or snapshot.probe_phase
    if ctx.needs_clarification or clarify_target:
        return MandatoryClass.CLARIFY
    if _important_to_share_eligible(snapshot, ctx):
        return MandatoryClass.IMPORTANT_TO_SHARE
    if _background_eligible(snapshot):
        return MandatoryClass.BACKGROUND_GOAL
    if _summary_close_eligible(snapshot, ctx):
        return MandatoryClass.SUMMARY_CLOSE
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
    if mandatory_class == MandatoryClass.ISSUE:
        return kind in {ActionKind.ASK_EPISODE, ActionKind.ACK_ONLY}
    if mandatory_class == MandatoryClass.CLARIFY:
        return kind == ActionKind.CLARIFY
    if mandatory_class == MandatoryClass.IMPORTANT_TO_SHARE:
        return kind == ActionKind.IMPORTANT_TO_SHARE
    if mandatory_class == MandatoryClass.BACKGROUND_GOAL:
        return kind == ActionKind.BACKGROUND_GOAL
    if mandatory_class == MandatoryClass.SUMMARY_CLOSE:
        return kind == ActionKind.SUMMARY_CLOSE
    if mandatory_class == MandatoryClass.ACK_ONLY:
        return kind == ActionKind.ACK_ONLY
    return False
