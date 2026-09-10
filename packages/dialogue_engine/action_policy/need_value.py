"""Per-need utility and dialogue obligation — not dimension-count heuristics."""

from __future__ import annotations

from packages.dialogue_engine.action_policy.snapshot import EpisodeSnapshot, PolicySnapshot

ASKABLE_NEEDS: tuple[str, ...] = ("temporal", "current", "severity", "functional_impact")

INFORMATION_VALUE: dict[str, float] = {
    "temporal": 0.72,
    "current": 0.88,
    "severity": 0.58,
    "functional_impact": 0.52,
}


def normalize_attribute(attribute: str | None) -> str | None:
    if not attribute:
        return None
    if attribute in ("onset", "duration", "temporal"):
        return "temporal"
    if attribute in ("current", "status"):
        return "current"
    return attribute


def episode_unknown_needs(ep: EpisodeSnapshot) -> tuple[str, ...]:
    return tuple(need for need in ASKABLE_NEEDS if not ep.need_known(need))


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


def need_information_value(
    ep: EpisodeSnapshot,
    need: str,
    *,
    last_question_need: str | None = None,
) -> float:
    base = INFORMATION_VALUE.get(need, 0.4)
    if core_needs_satisfied(ep) and need in ("severity", "functional_impact"):
        return base * 0.35
    if (
        need == "current"
        and ep.temporal_known
        and ep.severity_known
        and last_question_need != "severity"
    ):
        return base * 0.4
    return base


def need_ask_utility(snapshot: PolicySnapshot, ep: EpisodeSnapshot, need: str) -> float:
    if not ep.interrogation_eligible or ep.need_known(need):
        return 0.0
    info = need_information_value(ep, need, last_question_need=snapshot.last_question_need)
    if not any(
        (
            ep.temporal_known,
            ep.current_known,
            ep.severity_known,
            ep.functional_impact_known,
        )
    ):
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


def best_remaining_ask_utility(snapshot: PolicySnapshot) -> float:
    best = 0.0
    for ep in snapshot.episode_decision_queue():
        if not ep.interrogation_eligible:
            continue
        for need in episode_unknown_needs(ep):
            best = max(best, need_ask_utility(snapshot, ep, need))
    return best


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


def transition_preferred(snapshot: PolicySnapshot, *, answer_pending: bool = False) -> bool:
    if outstanding_pending_obligation(snapshot):
        return False
    return transition_utility(snapshot, answer_pending=answer_pending) > best_remaining_ask_utility(
        snapshot
    )


def need_utility_for_action(
    snapshot: PolicySnapshot,
    episode_id: str | None,
    need: str | None,
) -> float:
    if not episode_id or not need:
        return 0.0
    ep = snapshot.episode(episode_id)
    if ep is None:
        return 0.0
    return need_ask_utility(snapshot, ep, need)
