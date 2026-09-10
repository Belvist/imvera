"""Single source of truth for askable QuestionNeeds — no PolicySnapshot dependency."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.dialogue_engine.action_policy.snapshot import EpisodeSnapshot

ASKABLE_NEEDS: tuple[str, ...] = ("temporal", "current", "severity", "functional_impact")

# Attribute aliases → canonical askable need keys.
NEED_ALIASES: dict[str, str] = {
    "onset": "temporal",
    "duration": "temporal",
    "temporal": "temporal",
    "current": "current",
    "status": "current",
    "severity": "severity",
    "functional_impact": "functional_impact",
}


def normalize_attribute(attribute: str | None) -> str | None:
    if not attribute:
        return None
    return NEED_ALIASES.get(attribute, attribute)


def episode_unknown_needs(ep: EpisodeSnapshot) -> tuple[str, ...]:
    return tuple(need for need in ASKABLE_NEEDS if not ep.need_known(need))


def episode_has_any_known_askable(ep: EpisodeSnapshot) -> bool:
    return any(ep.need_known(need) for need in ASKABLE_NEEDS)
