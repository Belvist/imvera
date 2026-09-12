"""Information gain scoring for attribute questions."""

from __future__ import annotations

from packages.dialogue_engine.state import EngineState, IssueEpisode


def attribute_information_gain(
    state: EngineState,
    ep: IssueEpisode,
    attribute: str,
) -> float:
    """Higher = more useful to ask. Deterministic heuristic."""
    from packages.dialogue_engine.question_context import (
        attribute_need_satisfied,
        episode_is_resolved,
    )

    if episode_is_resolved(ep):
        return -1.0
    if attribute_need_satisfied(ep, attribute):
        return -1.0
    if ep.status == "resolved":
        return -0.5
    score = 1.0
    if attribute == "onset":
        score += 0.4
    if attribute == "duration" and "голов" in ep.primary_label.lower():
        score += 0.5
    if attribute == "severity":
        if "голов" in ep.primary_label.lower():
            # MVP parity: never ask severity before current/trend once temporal exists.
            if not attribute_need_satisfied(ep, "duration") and not attribute_need_satisfied(
                ep, "onset"
            ):
                return -1.0
            if not attribute_need_satisfied(ep, "current"):
                return -1.0
            score += 0.3
        else:
            score += 0.1
    if attribute == "current":
        temporal = (
            ep.known_attributes.get("onset") or ep.known_attributes.get("duration") or ""
        )
        if temporal:
            score += 0.55
        if "вчера" in temporal.lower() or "утр" in temporal.lower():
            score += 0.15
    improving = ep.known_attributes.get("status", "")
    if improving and any(
        w in improving.lower() for w in ("лучше", "прошл", "почти", "полегч")
    ):
        score -= 0.6
    asked = state.pending_episode_attribute == attribute
    if asked:
        score -= 0.3
    return score


def best_question_need(state: EngineState, ep: IssueEpisode):
    """Delegate to Dialogue Product Pack — scoring is no longer the owner."""
    from packages.dialogue_engine.product import next_product_need

    return next_product_need(state, ep)


def best_attribute_to_ask(state: EngineState, ep: IssueEpisode) -> str | None:
    from packages.dialogue_engine.question_context import (
        attribute_need_satisfied,
        episode_is_resolved,
    )

    if episode_is_resolved(ep):
        return None
    if getattr(ep, "kind", None) == "other":
        if ep.known_attributes.get("needs_help"):
            return None
        return "needs_help"
    pending = state.pending_episode_attribute
    if pending and not attribute_need_satisfied(ep, pending):
        return pending

    label = ep.primary_label.lower()
    ordered: tuple[str, ...]
    if ep.body_site == "живот" or "живот" in label:
        ordered = ("onset", "current", "severity")
    elif "голов" in label:
        # MVP: onset/duration → current/trend → severity (not severity before «а сейчас»).
        ordered = ("duration", "current", "severity")
    else:
        ordered = ("onset", "severity", "current")
    scored = [(a, attribute_information_gain(state, ep, a)) for a in ordered]
    scored = [(a, s) for a, s in scored if s > 0]
    if not scored:
        return None
    return max(scored, key=lambda x: x[1])[0]
