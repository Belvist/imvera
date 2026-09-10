"""Generic, auditable feature extraction for ActionPolicy."""

from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import ActionKind, CandidateAction, normalize_need
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView

_GAIN = {
    "temporal": 1.0,
    "current": 0.9,
    "severity": 0.65,
    "functional_impact": 0.55,
    "concern": 1.0,
}


def extract_features(
    snapshot: PolicySnapshot,
    ctx: TurnContextView,
    action: CandidateAction,
) -> dict[str, float]:
    features: dict[str, float] = {"bias": 1.0}
    features[f"action:{action.kind.value}"] = 1.0

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
        features["known_dimensions"] = float(ep.known_dimension_count if ep else 0)
        features["user_burden"] = snapshot.user_burden
        features["repeat_penalty"] = 1.0 if need and need == snapshot.last_question_need else 0.0

    features["fit:safety"] = 1.0 if action.kind == ActionKind.SAFETY and snapshot.risk_level == "urgent" else 0.0
    features["fit:goodbye"] = 1.0 if action.kind == ActionKind.GOODBYE_FINAL and ctx.explicit_farewell else 0.0
    features["fit:control"] = 1.0 if action.kind == ActionKind.CONTROL and ctx.control not in {"", "none", "stop_call"} else 0.0
    features["fit:repair"] = 1.0 if action.kind == ActionKind.REPAIR and ctx.repair else 0.0
    features["fit:answer_user"] = 1.0 if action.kind == ActionKind.ANSWER_USER and ctx.user_question else 0.0
    features["fit:meta"] = 1.0 if action.kind == ActionKind.LISTEN_META and (ctx.meta or ctx.unclear_without_grounding) else 0.0
    features["fit:clarify"] = 1.0 if action.kind == ActionKind.CLARIFY and (ctx.needs_clarification or ctx.clarify_target or snapshot.probe_phase) else 0.0
    features["fit:episode"] = 1.0 if action.kind == ActionKind.ASK_EPISODE and bool(snapshot.attention_episodes) else 0.0
    features["fit:its"] = 1.0 if action.kind == ActionKind.IMPORTANT_TO_SHARE and snapshot.wellness_entry_covered and not snapshot.attention_episodes else 0.0
    features["fit:background"] = 1.0 if action.kind == ActionKind.BACKGROUND_GOAL else 0.0
    features["fit:summary"] = 1.0 if action.kind == ActionKind.SUMMARY_CLOSE and snapshot.important_to_share_resolved else 0.0
    features["fit:ack"] = 1.0 if action.kind == ActionKind.ACK_ONLY else 0.0
    features["new_grounded_issue"] = 1.0 if ctx.has_new_issue else 0.0
    features["its_pending"] = 1.0 if snapshot.its_pending else 0.0
    return features
