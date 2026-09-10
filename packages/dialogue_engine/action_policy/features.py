"""Generic, auditable feature extraction for ActionPolicy."""

from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import (
    ActionKind,
    CandidateAction,
    normalize_need,
)
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView

_GAIN = {
    "temporal": 1.0,
    "current": 0.9,
    "severity": 0.65,
    "functional_impact": 0.55,
    "concern": 1.0,
}


def _nonterminal_control(ctx: TurnContextView) -> bool:
    return ctx.control not in {"", "none", "stop_call"}


def _clarify_signal(ctx: TurnContextView) -> bool:
    return bool(
        ctx.needs_clarification
        or ctx.unresolved_concern
        or ctx.clarify_target
    )


def _urgent_risk(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    return ctx.urgent_risk or snapshot.risk_level == "urgent"


def _remaining_information_value(ep: object | None) -> float:
    if ep is None:
        return 0.0
    unknown = sum(
        (
            0.0 if getattr(ep, "temporal_known", False) else 1.0,
            0.0 if getattr(ep, "current_known", False) else 1.0,
            0.0 if getattr(ep, "severity_known", False) else 1.0,
        )
    )
    return unknown / 3.0


def _its_context_fit(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    if not snapshot.wellness_entry_covered:
        return False
    if ctx.has_new_other_person_issue and not ctx.has_new_speaker_issue:
        return True
    if snapshot.transition_preferred(ctx):
        return True
    if (
        snapshot.user_burden >= 0.75
        and snapshot.questions_asked_this_episode >= 2
    ):
        return True
    return not snapshot.has_askable_open_issues


def extract_features(
    snapshot: PolicySnapshot,
    ctx: TurnContextView,
    action: CandidateAction,
) -> dict[str, float]:
    features: dict[str, float] = {"bias": 1.0}
    features[f"action:{action.kind.value}"] = 1.0
    transition_preferred = snapshot.transition_preferred(ctx)
    burden = snapshot.user_burden
    remaining_info = _remaining_information_value(snapshot.active_episode)

    if action.kind == ActionKind.ASK_EPISODE:
        ep = snapshot.episode(action.episode_id)
        need = normalize_need(action.question_need)
        gain = _GAIN.get(need or "", 0.4)
        dim_count = ep.known_dimension_count if ep else 0
        features["active_issue"] = 1.0 if ep is not None else 0.0
        features["information_gain"] = gain
        features["unanswered_dimension_value"] = gain * max(0.15, 1.0 - burden)
        features["remaining_information_value"] = remaining_info
        features["pending_need_match"] = (
            1.0
            if snapshot.pending_episode_attribute
            and need
            and (
                need == snapshot.pending_episode_attribute
                or (
                    need == "temporal"
                    and snapshot.pending_episode_attribute in {"onset", "duration", "temporal"}
                )
            )
            else 0.0
        )
        features["episode_resolving"] = 1.0 if ep and ep.resolving else 0.0
        features["known_dimensions"] = float(dim_count)
        features["enough_dimensions"] = 1.0 if dim_count >= 2 else 0.0
        features["ask_burden_penalty"] = burden
        features["episode_question_cost"] = float(snapshot.questions_asked_this_episode)
        features["repeat_penalty"] = (
            1.0 if need and need == snapshot.last_question_need else 0.0
        )
        features["transition_penalty"] = 1.0 if transition_preferred else 0.0
        features["useful_follow_up"] = (
            remaining_info
            if ep
            and ep.interrogation_eligible
            and ep.has_open_questions
            and need
            and need != snapshot.last_question_need
            else 0.0
        )
        features["fit:episode"] = (
            1.0
            if ep and ep.interrogation_eligible and ep.has_open_questions
            else 0.0
        )

    clarify_on = _clarify_signal(ctx)
    its_on = _its_context_fit(snapshot, ctx)

    features["fit:safety"] = (
        1.0 if action.kind == ActionKind.SAFETY and _urgent_risk(snapshot, ctx) else 0.0
    )
    features["fit:goodbye"] = (
        1.0 if action.kind == ActionKind.GOODBYE_FINAL and ctx.explicit_farewell else 0.0
    )
    features["fit:control"] = (
        1.0 if action.kind == ActionKind.CONTROL and _nonterminal_control(ctx) else 0.0
    )
    features["fit:repair"] = 1.0 if action.kind == ActionKind.REPAIR and ctx.repair else 0.0
    features["fit:answer_user"] = (
        1.0 if action.kind == ActionKind.ANSWER_USER and ctx.user_question else 0.0
    )
    features["fit:meta"] = (
        1.0
        if action.kind == ActionKind.LISTEN_META
        and (ctx.meta or ctx.unclear_without_grounding)
        else 0.0
    )
    features["fit:clarify"] = 1.0 if action.kind == ActionKind.CLARIFY and clarify_on else 0.0
    features["fit:its"] = 1.0 if action.kind == ActionKind.IMPORTANT_TO_SHARE and its_on else 0.0
    features["fit:background"] = 1.0 if action.kind == ActionKind.BACKGROUND_GOAL else 0.0
    features["fit:summary"] = (
        1.0
        if action.kind == ActionKind.SUMMARY_CLOSE and snapshot.important_to_share_resolved
        else 0.0
    )
    features["fit:ack"] = 1.0 if action.kind == ActionKind.ACK_ONLY else 0.0
    features["new_grounded_issue"] = 1.0 if ctx.has_new_speaker_issue else 0.0
    features["its_pending"] = 1.0 if snapshot.its_pending else 0.0
    if action.kind == ActionKind.IMPORTANT_TO_SHARE:
        features["transition_preferred"] = 1.0 if transition_preferred else 0.0
        question_pressure = min(1.0, snapshot.questions_asked_this_episode / 2.0)
        features["transition_burden_relief"] = burden * question_pressure
        features["remaining_information_value"] = 1.0 - remaining_info
    return features
