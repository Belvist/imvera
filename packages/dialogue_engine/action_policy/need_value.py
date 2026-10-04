"""Per-need utility and dialogue obligation — not dimension-count heuristics."""

from __future__ import annotations

from packages.dialogue_engine.action_policy.needs import (
    ASKABLE_NEEDS,
    episode_has_any_known_askable,
    episode_unknown_needs,
    normalize_attribute,
)
from packages.dialogue_engine.action_policy.snapshot import (
    EpisodeSnapshot,
    PolicySnapshot,
    TurnContextView,
)

INFORMATION_VALUE: dict[str, float] = {
    "temporal": 0.72,
    "current": 0.88,
    "severity": 0.58,
    "functional_impact": 0.52,
}


def interrogation_intentionally_left(snapshot: PolicySnapshot) -> bool:
    """ITS ask/resolve marks intentional leave of optional interrogation."""
    return snapshot.important_to_share_asked or snapshot.important_to_share_resolved


def core_needs_satisfied(ep: EpisodeSnapshot) -> bool:
    return ep.temporal_known and ep.current_known


def is_pending_obligation(snapshot: PolicySnapshot, episode_id: str, need: str) -> bool:
    pending = normalize_attribute(snapshot.pending_episode_attribute)
    if not pending or snapshot.active_episode_id != episode_id:
        return False
    return pending == need


def outstanding_pending_obligation(snapshot: PolicySnapshot) -> bool:
    """Unsettled pending_episode_attribute on the active speaker episode."""
    pending = normalize_attribute(snapshot.pending_episode_attribute)
    if not pending or not snapshot.active_episode_id:
        return False
    ep = snapshot.episode(snapshot.active_episode_id)
    if ep is None or not ep.interrogation_eligible:
        return False
    return not ep.need_known(pending)


def hard_blocking_obligation(snapshot: PolicySnapshot) -> bool:
    """Conversational obligations that must not be silently discarded."""
    return outstanding_pending_obligation(snapshot)


def episode_reopens_interrogation(snapshot: PolicySnapshot, ep: EpisodeSnapshot) -> bool:
    """After ITS leave, only fresh/pending-work episodes reopen optional asks."""
    if not ep.speaker_owned or not ep.interrogation_eligible or ep.resolving:
        return False
    if outstanding_pending_obligation(snapshot) and ep.episode_id == snapshot.active_episode_id:
        return True
    # Brand-new / never-started episode still needs first-touch interrogation.
    return not episode_has_any_known_askable(ep)


def turn_reopens_interrogation(ctx: TurnContextView | None) -> bool:
    """New grounded speaker evidence may reopen episode handling after ITS leave."""
    if ctx is None:
        return False
    return bool(ctx.has_new_speaker_issue or ctx.has_new_issue)


def need_is_currently_askable(
    snapshot: PolicySnapshot,
    ep: EpisodeSnapshot,
    need: str,
    *,
    ctx: TurnContextView | None = None,
) -> bool:
    """Whether an unresolved askable need may generate/score an ASK this turn."""
    if not ep.interrogation_eligible or ep.need_known(need) or ep.resolving:
        return False
    if is_pending_obligation(snapshot, ep.episode_id, need):
        return True
    if not interrogation_intentionally_left(snapshot):
        return True
    if turn_reopens_interrogation(ctx):
        return True
    # After intentional leave: optional leftovers stay optional, not askable.
    return episode_reopens_interrogation(snapshot, ep)


def valuable_optional_need(
    snapshot: PolicySnapshot,
    ep: EpisodeSnapshot,
    need: str,
    *,
    ctx: TurnContextView | None = None,
) -> bool:
    """Unresolved optional need that still competes in ASK vs TRANSITION utility."""
    if is_pending_obligation(snapshot, ep.episode_id, need):
        return False
    if not need_is_currently_askable(snapshot, ep, need, ctx=ctx):
        return False
    return need_ask_utility(snapshot, ep, need, ctx=ctx) > 0.0


def has_hard_blocking_episode_work(
    snapshot: PolicySnapshot,
    *,
    ctx: TurnContextView | None = None,
) -> bool:
    """
    Hard progression blocker.

    Optional unresolved needs are NOT hard blockers after interrogation leave.
    Pending obligations, reopenable fresh episodes, and new-turn evidence still are.
    """
    if hard_blocking_obligation(snapshot):
        return True
    if interrogation_intentionally_left(snapshot):
        if turn_reopens_interrogation(ctx):
            return any(
                ep.interrogation_eligible and episode_unknown_needs(ep) and not ep.resolving
                for ep in snapshot.episodes
                if ep.speaker_owned
            )
        return any(episode_reopens_interrogation(snapshot, ep) for ep in snapshot.episodes)
    return any(
        ep.interrogation_eligible and episode_unknown_needs(ep) and not ep.resolving
        for ep in snapshot.episodes
        if ep.speaker_owned
    )


def need_information_value(
    ep: EpisodeSnapshot,
    need: str,
    *,
    last_question_need: str | None = None,
) -> float:
    base = INFORMATION_VALUE.get(need, 0.4)
    if core_needs_satisfied(ep) and need in ("severity", "functional_impact"):
        # Fresh temporal probe just delivered (e.g. duration answered this
        # turn): the severity follow-up is the expected flow — keep full value
        # so the transition heuristic does not cut probing short (fs-77afbbf1).
        # Stale core (no recent temporal question, e.g. dev_two_dims_finish)
        # keeps the devaluation so ITS can win.
        if (
            need == "severity"
            and not ep.severity_known
            and last_question_need == "temporal"
        ):
            return base
        return base * 0.35
    if (
        need == "current"
        and ep.temporal_known
        and ep.severity_known
        and last_question_need != "severity"
    ):
        return base * 0.4
    return base


def need_ask_utility(
    snapshot: PolicySnapshot,
    ep: EpisodeSnapshot,
    need: str,
    *,
    ctx: TurnContextView | None = None,
) -> float:
    if not need_is_currently_askable(snapshot, ep, need, ctx=ctx):
        return 0.0
    info = need_information_value(ep, need, last_question_need=snapshot.last_question_need)
    if not episode_has_any_known_askable(ep):
        if need == "temporal":
            info += 0.28
        else:
            info *= 0.55
    obligation = 1.0 if is_pending_obligation(snapshot, ep.episode_id, need) else 0.0
    repeated = 1.0 if snapshot.last_question_need == need else 0.0
    burden = snapshot.user_burden
    question_cost = min(1.0, snapshot.questions_asked_this_episode / 4.0)
    active_bonus = 0.12 if ep.episode_id == snapshot.active_episode_id else 0.0
    queue_bonus = 0.08 if ep.episode_id in snapshot.pending_episode_ids else 0.0
    resolving_penalty = 0.35 if ep.resolving else 0.0
    return (
        info
        + obligation * 1.3
        + active_bonus
        + queue_bonus
        - burden * 0.5
        - question_cost * 0.35
        - repeated * 0.5
        - resolving_penalty
    )


def best_remaining_ask_utility(
    snapshot: PolicySnapshot,
    *,
    ctx: TurnContextView | None = None,
) -> float:
    best = 0.0
    for episode_id, need in currently_askable_needs(snapshot, ctx=ctx):
        ep = snapshot.episode(episode_id)
        if ep is not None:
            best = max(best, need_ask_utility(snapshot, ep, need, ctx=ctx))
    return best


def currently_askable_needs(
    snapshot: PolicySnapshot,
    *,
    ctx: TurnContextView | None = None,
) -> tuple[tuple[str, str], ...]:
    """(episode_id, need) pairs that utility/candidates may consider this turn."""
    pairs: list[tuple[str, str]] = []
    for ep in snapshot.episode_decision_queue():
        needs = list(episode_unknown_needs(ep))
        # A reducer-owned pending need is legal even when it is outside the
        # generic optional catalogue. Candidate generation and utility share
        # this one set; do not add a second product/clinical need registry.
        if ep.episode_id == snapshot.active_episode_id and outstanding_pending_obligation(snapshot):
            pending = normalize_attribute(snapshot.pending_episode_attribute)
            if pending and pending not in needs:
                needs.append(pending)
        for need in needs:
            if need_is_currently_askable(snapshot, ep, need, ctx=ctx):
                pairs.append((ep.episode_id, need))
    return tuple(pairs)


def transition_utility(snapshot: PolicySnapshot, *, answer_pending: bool = False) -> float:
    if not snapshot.wellness_entry_covered:
        return 0.0
    burden = snapshot.user_burden
    question_pressure = min(1.0, snapshot.questions_asked_this_episode / 2.0)
    resolving = 0.0
    core_complete = 0.0
    for ep in snapshot.episode_decision_queue():
        if ep.resolving:
            resolving = 1.0
        if core_needs_satisfied(ep):
            core_complete = 0.48
        if (
            ep.temporal_known
            and ep.severity_known
            and snapshot.last_question_need != "severity"
        ):
            core_complete = max(core_complete, 0.55)
    pending_answer = 0.18 if answer_pending and core_complete else 0.0
    return (
        burden * 0.55 * question_pressure
        + resolving * 0.42
        + core_complete
        + pending_answer
    )


def transition_preferred(
    snapshot: PolicySnapshot,
    *,
    answer_pending: bool = False,
    ctx: TurnContextView | None = None,
) -> bool:
    if hard_blocking_obligation(snapshot):
        return False
    if interrogation_intentionally_left(snapshot) and not has_hard_blocking_episode_work(
        snapshot, ctx=ctx
    ):
        return True
    return transition_utility(snapshot, answer_pending=answer_pending) > best_remaining_ask_utility(
        snapshot, ctx=ctx
    )


def need_utility_for_action(
    snapshot: PolicySnapshot,
    episode_id: str | None,
    need: str | None,
    *,
    ctx: TurnContextView | None = None,
) -> float:
    if not episode_id or not need:
        return 0.0
    ep = snapshot.episode(episode_id)
    if ep is None:
        return 0.0
    return need_ask_utility(snapshot, ep, need, ctx=ctx)


# Re-export for callers that historically imported from need_value.
__all__ = [
    "ASKABLE_NEEDS",
    "best_remaining_ask_utility",
    "currently_askable_needs",
    "episode_unknown_needs",
    "hard_blocking_obligation",
    "has_hard_blocking_episode_work",
    "interrogation_intentionally_left",
    "is_pending_obligation",
    "need_ask_utility",
    "need_information_value",
    "need_is_currently_askable",
    "need_utility_for_action",
    "normalize_attribute",
    "outstanding_pending_obligation",
    "transition_preferred",
    "transition_utility",
    "valuable_optional_need",
]
