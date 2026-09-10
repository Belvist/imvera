"""Pure ActionPolicy: candidates -> hard constraints -> linear score -> choose."""

from __future__ import annotations

from collections.abc import Mapping

from packages.dialogue_engine.action_policy.actions import (
    ActionKind,
    CandidateAction,
    PolicyConstraintViolation,
    PolicyDecision,
)
from packages.dialogue_engine.action_policy.constraints import reject_candidate
from packages.dialogue_engine.action_policy.mandatory import compute_mandatory_class
from packages.dialogue_engine.action_policy.scorer import (
    DEFAULT_WEIGHTS,
    POLICY_VERSION,
    score_action,
)
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView
from packages.dialogue_engine.question_context import QuestionNeed


def _append_unique(items: list[CandidateAction], action: CandidateAction) -> None:
    if action not in items:
        items.append(action)


def generate_candidates(
    snapshot: PolicySnapshot,
    ctx: TurnContextView,
) -> tuple[CandidateAction, ...]:
    """Generate a small generic set; no body-site or symptom-specific branches."""
    out: list[CandidateAction] = [
        CandidateAction(ActionKind.SAFETY),
        CandidateAction(ActionKind.IMPORTANT_TO_SHARE),
        CandidateAction(ActionKind.SUMMARY_CLOSE),
        CandidateAction(ActionKind.ACK_ONLY),
    ]

    if ctx.explicit_farewell:
        _append_unique(out, CandidateAction(ActionKind.GOODBYE_FINAL))
    if ctx.control not in {"", "none", "stop_call"}:
        _append_unique(out, CandidateAction(ActionKind.CONTROL, control=ctx.control))
    if ctx.repair:
        _append_unique(out, CandidateAction(ActionKind.REPAIR))
    if ctx.user_question:
        _append_unique(out, CandidateAction(ActionKind.ANSWER_USER))
    if ctx.meta or (snapshot.its_pending and ctx.unclear_without_grounding):
        _append_unique(out, CandidateAction(ActionKind.LISTEN_META))

    unresolved = ctx.unresolved_concern
    clarify_target = ctx.clarify_target or ("concern" if unresolved else None)
    if ctx.needs_clarification or unresolved or clarify_target:
        _append_unique(
            out,
            CandidateAction(
                ActionKind.CLARIFY,
                clarify_target=clarify_target or "concern",
            ),
        )

    for ep in snapshot.attention_episodes:
        attrs: list[str] = []
        if (
            snapshot.active_episode_id == ep.episode_id
            and snapshot.pending_episode_attribute
        ):
            attrs.append(snapshot.pending_episode_attribute)
        if not ep.temporal_known:
            attrs.append("onset")
        if not ep.current_known:
            attrs.append("current")
        if not ep.severity_known:
            attrs.append("severity")
        if snapshot.pending_episode_attribute == "functional_impact":
            attrs.append("functional_impact")
        for attr in attrs:
            _append_unique(
                out,
                CandidateAction(
                    ActionKind.ASK_EPISODE,
                    episode_id=ep.episode_id,
                    question_need=QuestionNeed.for_attribute(attr),
                ),
            )

    for goal in ("wellness", "mood", "sleep", "plans"):
        if snapshot.mandatory_background_goals or goal in snapshot.required_background_goals:
            _append_unique(
                out,
                CandidateAction(ActionKind.BACKGROUND_GOAL, target_goal=goal),
            )

    return tuple(out)


def choose(
    snapshot: PolicySnapshot,
    ctx: TurnContextView,
    *,
    weights: Mapping[str, float] | None = None,
) -> PolicyDecision:
    """ZERO MUTATION: only local lists/dicts are created."""
    mandatory_class = compute_mandatory_class(snapshot, ctx)
    survivors = []
    rejected = []
    for action in generate_candidates(snapshot, ctx):
        reason = reject_candidate(snapshot, ctx, action, mandatory_class=mandatory_class)
        if reason is not None:
            rejected.append(reason)
            continue
        survivors.append(
            score_action(
                snapshot,
                ctx,
                action,
                weights=weights or DEFAULT_WEIGHTS,
            )
        )

    if not survivors:
        raise PolicyConstraintViolation(
            mandatory_class=mandatory_class.value,
            rejected=tuple(rejected),
        )

    ranked = sorted(
        survivors,
        key=lambda item: (-item.score, item.action.key.label()),
    )
    return PolicyDecision(
        chosen=ranked[0].action,
        candidates=tuple(ranked),
        rejected=tuple(rejected),
        policy_version=POLICY_VERSION,
    )
