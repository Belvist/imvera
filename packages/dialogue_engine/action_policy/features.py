"""Generic, auditable feature extraction for ActionPolicy."""

from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import (
    ActionKind,
    CandidateAction,
    normalize_need,
)
from packages.dialogue_engine.action_policy.need_value import (
    best_remaining_ask_utility,
    need_ask_utility,
    need_information_value,
    normalize_attribute,
    transition_utility,
)
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView


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


def _its_context_fit(snapshot: PolicySnapshot, ctx: TurnContextView) -> bool:
    if not snapshot.wellness_entry_covered:
        return False
    if snapshot.outstanding_pending_obligation():
        return False
    if ctx.has_new_other_person_issue and not ctx.has_new_speaker_issue:
        return True
    if snapshot.transition_preferred(ctx):
        return True
    if (
        snapshot.user_burden >= 0.75
        and snapshot.questions_asked_this_episode >= 2
        and best_remaining_ask_utility(snapshot) < 0.42
    ):
        return True
    return best_remaining_ask_utility(snapshot) < 0.25


def extract_features(
    snapshot: PolicySnapshot,
    ctx: TurnContextView,
    action: CandidateAction,
) -> dict[str, float]:
    features: dict[str, float] = {"bias": 1.0}
    features[f"action:{action.kind.value}"] = 1.0
    transition_preferred = snapshot.transition_preferred(ctx)
    burden = snapshot.user_burden
    best_ask = best_remaining_ask_utility(snapshot)
    trans_util = transition_utility(snapshot, answer_pending=ctx.answers_pending_question)

    if action.kind == ActionKind.ASK_EPISODE:
        ep = snapshot.episode(action.episode_id)
        need = normalize_need(action.question_need)
        need_util = need_ask_utility(snapshot, ep, need) if ep and need else 0.0
        info = (
            need_information_value(ep, need, last_question_need=snapshot.last_question_need)
            if ep and need
            else 0.0
        )
        features["active_issue"] = 1.0 if ep is not None else 0.0
        features["information_value"] = info
        features["need_ask_utility"] = need_util
        pending_need = normalize_attribute(snapshot.pending_episode_attribute)
        features["pending_obligation"] = (
            1.0
            if ep
            and need
            and snapshot.outstanding_pending_obligation()
            and snapshot.active_episode_id == ep.episode_id
            and need == pending_need
            else 0.0
        )
        features["episode_resolving"] = 1.0 if ep and ep.resolving else 0.0
        features["ask_burden_penalty"] = burden
        features["episode_question_cost"] = float(snapshot.questions_asked_this_episode)
        features["repeat_penalty"] = (
            1.0 if need and need == snapshot.last_question_need else 0.0
        )
        features["transition_penalty"] = 1.0 if transition_preferred else 0.0
        features["fit:episode"] = 1.0 if need_util > 0.0 else 0.0

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
    if action.kind == ActionKind.IMPORTANT_TO_SHARE and its_on:
        features["transition_preferred"] = 1.0 if transition_preferred else 0.0
        question_pressure = min(1.0, snapshot.questions_asked_this_episode / 2.0)
        features["transition_burden_relief"] = burden * question_pressure
        features["transition_utility"] = trans_util
        features["best_remaining_need_penalty"] = best_ask
    return features
