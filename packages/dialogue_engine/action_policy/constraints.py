"""Non-learnable ActionPolicy constitution: reject, never merely penalize."""

from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import (
    ActionKind,
    CandidateAction,
    ConstraintRejection,
    normalize_need,
)
from packages.dialogue_engine.action_policy.mandatory import (
    MandatoryClass,
    action_matches_mandatory_class,
    compute_mandatory_class,
)
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView


def _reject(action: CandidateAction, rule_id: str, reason: str) -> ConstraintRejection:
    return ConstraintRejection(action=action, rule_id=rule_id, reason=reason)


def reject_candidate(
    snapshot: PolicySnapshot,
    ctx: TurnContextView,
    action: CandidateAction,
    *,
    mandatory_class: MandatoryClass | None = None,
) -> ConstraintRejection | None:
    kind = action.kind
    mandatory = mandatory_class or compute_mandatory_class(snapshot, ctx)
    if not action_matches_mandatory_class(action, mandatory, snapshot, ctx):
        return _reject(
            action,
            "mandatory_class_mismatch",
            f"mandatory class {mandatory} does not allow {kind.value}",
        )

    has_nonterminal_control = ctx.control not in {"", "none", "stop_call"}

    if kind == ActionKind.SAFETY and snapshot.risk_level != "urgent":
        return _reject(action, "safety_not_present", "no urgent safety state")

    if kind == ActionKind.GOODBYE_FINAL and not ctx.explicit_farewell:
        return _reject(action, "farewell_not_present", "goodbye requires explicit farewell")

    if kind == ActionKind.CONTROL:
        if not has_nonterminal_control or action.control != ctx.control:
            return _reject(action, "control_mismatch", "control candidate must match current control")

    if kind == ActionKind.REPAIR and not ctx.repair:
        return _reject(action, "repair_not_present", "no repair request")

    if kind == ActionKind.ANSWER_USER and not ctx.user_question:
        return _reject(action, "user_question_not_present", "no user question")

    if kind == ActionKind.LISTEN_META:
        allowed = ctx.meta or (snapshot.its_pending and ctx.unclear_without_grounding)
        if not allowed:
            return _reject(action, "meta_not_present", "LISTEN_META requires meta/unclear turn")
        if ctx.has_grounded_information:
            return _reject(action, "grounded_info_not_meta", "grounded information must be handled, not parked")

    attention = snapshot.attention_episodes
    if kind == ActionKind.ASK_EPISODE:
        ep = snapshot.episode(action.episode_id)
        if ep is None:
            return _reject(action, "episode_missing", "target episode does not exist")
        if not ep.speaker_owned:
            return _reject(action, "wrong_subject", "other-person issue cannot drive speaker interrogation")
        if not ep.needs_attention:
            return _reject(action, "episode_low_value", "episode does not justify another question")
        if action.question_need is None:
            return _reject(action, "question_need_missing", "episode question requires semantic need")
        if ep.need_known(action.question_need):
            return _reject(action, "already_known", "requested semantic need already satisfied")
        need = normalize_need(action.question_need)
        if snapshot.last_question_need and need == snapshot.last_question_need:
            return _reject(action, "repeat_question", "same semantic question was just asked")

    if kind == ActionKind.BACKGROUND_GOAL:
        if attention:
            return _reject(action, "active_issue_blocks_background", "issue has higher priority")
        goal = action.target_goal or ""
        required = snapshot.mandatory_background_goals or goal in snapshot.required_background_goals
        if not required:
            return _reject(action, "background_optional", "UNSEEN background goal is not mandatory")
        if snapshot.background_status(goal) not in {"unseen", "asked"}:
            return _reject(action, "background_done", "background goal already covered")
        if snapshot.its_pending:
            return _reject(action, "its_blocks_background", "pending ITS response has higher priority")

    if kind == ActionKind.IMPORTANT_TO_SHARE:
        if attention:
            return _reject(action, "active_issue_blocks_its", "active useful issue question comes first")
        if ctx.has_new_issue:
            return _reject(action, "new_issue_blocks_its", "new grounded issue must be handled first")
        if not snapshot.wellness_entry_covered:
            return _reject(action, "entry_not_covered", "wellness entry is not yet covered")
        if snapshot.important_to_share_asked or snapshot.important_to_share_resolved:
            return _reject(action, "its_already_used", "IMPORTANT_TO_SHARE is bounded")

    if kind == ActionKind.SUMMARY_CLOSE:
        if attention:
            return _reject(action, "premature_close_issue", "open useful issue blocks close")
        if ctx.has_new_issue:
            return _reject(action, "premature_close_new_issue", "new grounded issue blocks close")
        if not snapshot.important_to_share_resolved:
            return _reject(action, "premature_close_its", "close requires resolved IMPORTANT_TO_SHARE")
        if ctx.meta or ctx.unclear_without_grounding:
            return _reject(action, "premature_close_meta", "meta/unclear text cannot close conversation")

    if kind == ActionKind.CLARIFY:
        target = action.clarify_target
        wanted = ctx.clarify_target or snapshot.probe_phase
        if not (ctx.needs_clarification or wanted):
            return _reject(action, "clarify_not_needed", "no clarification need")
        if target != wanted and wanted:
            return _reject(action, "clarify_target_mismatch", "clarification target mismatch")
        if attention:
            return _reject(action, "issue_replaces_generic_clarify", "grounded issue owns the turn")

    return None
