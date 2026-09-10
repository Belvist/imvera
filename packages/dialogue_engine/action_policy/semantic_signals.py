"""Canonical semantic signals for ActionPolicy — no legacy check_path/probe inputs."""

from __future__ import annotations

_WELLNESS_NEGATIVE = frozenset({"negative", "uncertain", "bad", "poor"})


def has_grounded_speaker_issue(issue_mentions: tuple[object, ...]) -> bool:
    return bool(issue_mentions)


def wellness_polarity_negative(goal_facts: tuple[object, ...]) -> bool:
    for fact in goal_facts:
        if getattr(fact, "field", None) != "wellness":
            continue
        value = str(getattr(fact, "value", "")).strip().lower()
        if value in _WELLNESS_NEGATIVE:
            return True
    return False


def derive_unresolved_concern(
    *,
    issue_mentions: tuple[object, ...] = (),
    goal_facts: tuple[object, ...] = (),
    kernel_ambiguities: tuple[str, ...] = (),
    needs_clarification: bool = False,
) -> bool:
    """Negative/uncertain wellness without a grounded speaker issue → clarify concern."""
    if has_grounded_speaker_issue(issue_mentions):
        return False
    if needs_clarification:
        return True
    if "vague_issue" in kernel_ambiguities:
        return True
    return wellness_polarity_negative(goal_facts)
