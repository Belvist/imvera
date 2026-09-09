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
            if not attribute_need_satisfied(ep, "duration"):
                return -1.0
            score += 0.3
        else:
            score += 0.1
    if attribute == "current":
        if ep.known_attributes.get("onset") and "вчера" in ep.known_attributes["onset"].lower():
            score += 0.5
    improving = ep.known_attributes.get("status", "")
    if improving and any(w in improving.lower() for w in ("лучше", "прошл", "почти")):
        score -= 0.6
    asked = state.pending_episode_attribute == attribute
    if asked:
        score -= 0.3
    return score


def best_question_need(state: EngineState, ep: IssueEpisode):
    """Return single or compound QuestionNeed for the highest-gain gap."""
    from packages.dialogue_engine.issue_memory import _needs_severity
    from packages.dialogue_engine.question_context import (
        QuestionNeed,
        attribute_need_satisfied,
        episode_is_resolved,
        question_need_satisfied,
    )

    if episode_is_resolved(ep):
        return None
    pending = state.pending_episode_attribute
    if pending:
        need = QuestionNeed.for_attribute(pending)
        if not question_need_satisfied(ep, need):
            return need

    onset_ok = (
        attribute_need_satisfied(ep, "onset") or attribute_need_satisfied(ep, "duration")
    )
    current_ok = attribute_need_satisfied(ep, "current")
    label = ep.primary_label.lower()
    is_abdominal = ep.body_site == "живот" or "живот" in label

    if not onset_ok and not current_ok and is_abdominal:
        return QuestionNeed.compound("onset", "current")
    if not onset_ok and not current_ok and "голов" in label:
        return QuestionNeed.compound("duration", "current")

    attr = best_attribute_to_ask(state, ep)
    if attr:
        return QuestionNeed.for_attribute(attr)
    if not current_ok and is_abdominal:
        return QuestionNeed.for_attribute("current")
    if _needs_severity(ep) and "severity" not in ep.known_attributes:
        return QuestionNeed.for_attribute("severity")
    return None


def best_attribute_to_ask(state: EngineState, ep: IssueEpisode) -> str | None:
    from packages.dialogue_engine.question_context import (
        attribute_need_satisfied,
        episode_is_resolved,
    )

    if episode_is_resolved(ep):
        return None
    pending = state.pending_episode_attribute
    if pending and not attribute_need_satisfied(ep, pending):
        return pending

    label = ep.primary_label.lower()
    ordered: tuple[str, ...]
    if ep.body_site == "живот" or "живот" in label:
        ordered = ("onset", "current", "severity")
    elif "голов" in label:
        ordered = ("duration", "severity", "current")
    else:
        ordered = ("onset", "severity", "current")
    scored = [(a, attribute_information_gain(state, ep, a)) for a in ordered]
    scored = [(a, s) for a, s in scored if s > 0]
    if not scored:
        return None
    return max(scored, key=lambda x: x[1])[0]
