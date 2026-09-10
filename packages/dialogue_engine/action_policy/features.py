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


def extract_features(
    snapshot: PolicySnapshot,
    ctx: TurnContextView,
    action: CandidateAction,
) -> dict[str, float]:
    features: dict[str, float] = {"bias": 1.0}
    features[f"action:{action.kind.value}"] = 1.0
    transition_preferred = snapshot.transition_preferred(ctx)

    if action.kind == ActionKind.ASK_EPISODE:
        ep = snapshot.episode(action.episode_id)
        need = normalize_need(action.question_need)
        features["active_issue"] = 1.0 if ep is not None else 0.0
        features["information_gain"] = _GAIN.get(need or "", 0.4)
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
        dim_count = ep.known_dimension_count if ep else 0
        features["known_dimensions"] = float(dim_count)
        features["enough_dimensions"] = 1.0 if dim_count >= 2 else 0.0
        features["user_burden"] = snapshot.user_burden
        features["repeat_penalty"] = (
            1.0 if need and need == snapshot.last_question_need else 0.0
        )
        features["transition_penalty"] = 1.0 if transition_preferred else 0.0

    clarify_signal = (
        ctx.needs_clarification
        or ctx.unresolved_concern
        or ctx.clarify_target
        or snapshot.probe_phase
        or snapshot.unresolved_concern
    )
    its_signal = snapshot.wellness_entry_covered and (
        transition_preferred or not snapshot.pressing_interrogation_episodes
    )

    features["fit:safety"] = (
        1.0 if action.kind == ActionKind.SAFETY and snapshot.risk_level == "urgent" else 0.0
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
    features["fit:clarify"] = 1.0 if action.kind == ActionKind.CLARIFY and clarify_signal else 0.0
    worthwhile = action.kind == ActionKind.ASK_EPISODE and any(
        ep.episode_id == action.episode_id and ep.worthwhile_followup
        for ep in snapshot.attention_episodes
    )
    features["fit:episode"] = 1.0 if worthwhile else 0.0
    features["fit:its"] = (
        1.0 if action.kind == ActionKind.IMPORTANT_TO_SHARE and its_signal else 0.0
    )
    features["fit:background"] = 1.0 if action.kind == ActionKind.BACKGROUND_GOAL else 0.0
    features["fit:summary"] = (
        1.0
        if action.kind == ActionKind.SUMMARY_CLOSE and snapshot.important_to_share_resolved
        else 0.0
    )
    features["fit:ack"] = 1.0 if action.kind == ActionKind.ACK_ONLY else 0.0
    features["new_grounded_issue"] = 1.0 if ctx.has_new_issue else 0.0
    features["its_pending"] = 1.0 if snapshot.its_pending else 0.0
    if action.kind == ActionKind.IMPORTANT_TO_SHARE:
        features["transition_preferred"] = 1.0 if transition_preferred else 0.0
    return features
