"""What we already know — do not ask again.

Product rule: next question = plan_steps − known(facts from this call / episode).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState, IssueEpisode

_TEMPORAL_KEYS = ("onset", "duration")
_EMPTY = frozenset({"", "unknown", "active", "none", "null"})


def _attr(ep: IssueEpisode, name: str) -> str:
    return str((ep.known_attributes or {}).get(name) or "").strip()


def _meaningful(val: str) -> bool:
    return bool(val) and val.lower() not in _EMPTY


def episode_evidence_blob(ep: IssueEpisode) -> str:
    parts = [
        ep.primary_label or "",
        *(m.label or "" for m in ep.mentions),
        *(
            (m.evidence.quote or "")
            for m in ep.mentions
            if getattr(m, "evidence", None) is not None
        ),
        *(_attr(ep, k) for k in ("onset", "duration", "current", "severity", "associated")),
    ]
    return " ".join(p for p in parts if p).lower()


def temporal_known_on_episode(ep: IssueEpisode) -> bool:
    """True when this episode already has when/how-long."""
    for key in _TEMPORAL_KEYS:
        if _meaningful(_attr(ep, key)):
            return True
    blob = episode_evidence_blob(ep)
    # Free-speech already carried time without a filled slot.
    return any(
        x in blob
        for x in (
            "с утра",
            "утром",
            "вчера",
            "сегодня",
            "с ночи",
            "ночью",
            "с вечера",
            "неделю",
            "дня два",
            "два дня",
            "несколько дн",
        )
    )


def severity_known_on_episode(ep: IssueEpisode) -> bool:
    if _meaningful(_attr(ep, "severity")):
        return True
    blob = episode_evidence_blob(ep)
    return any(
        x in blob
        for x in (
            "сильн",
            "терпим",
            "невыносим",
            "слабая боль",
            "слабая",
            "умеренн",
            "усилива",
        )
    )


def current_known_on_episode(ep: IssueEpisode) -> bool:
    return _meaningful(_attr(ep, "current"))


def nausea_mentioned_on_episode(ep: IssueEpisode) -> bool:
    blob = episode_evidence_blob(ep)
    return "тошн" in blob


def nausea_mentioned_in_call(state: EngineState) -> bool:
    for ep in (state.issue_episodes or {}).values():
        if nausea_mentioned_on_episode(ep):
            return True
    return False


def call_has_temporal_answer(state: EngineState) -> bool:
    """Any episode already answered when/how-long this call."""
    for ep in (state.issue_episodes or {}).values():
        for key in _TEMPORAL_KEYS:
            val = _attr(ep, key)
            if _meaningful(val):
                return True
    return False


@dataclass(frozen=True)
class CallKnownFacts:
    """Call-level facts used to skip redundant questions."""

    has_temporal: bool
    has_nausea: bool
    family_ask_counts: dict[str, int]
    content_asks: int


def snapshot_call_known(state: EngineState) -> CallKnownFacts:
    families: dict[str, int] = dict(getattr(state, "product_asks_by_family", {}) or {})
    return CallKnownFacts(
        has_temporal=call_has_temporal_answer(state),
        has_nausea=nausea_mentioned_in_call(state),
        family_ask_counts=families,
        content_asks=int(getattr(state, "product_content_asks", 0) or 0),
    )


def step_already_known(
    state: EngineState,
    ep: IssueEpisode,
    step: str,
    *,
    family: str = "",
) -> bool:
    """Whether this plan step should be skipped (already known / redundant)."""
    if step in ("onset", "duration"):
        if temporal_known_on_episode(ep):
            return True
        # Abdomen after another issue already got «когда» — do not re-ask.
        if family == "abdominal" and call_has_temporal_answer(state):
            return True
        return False
    if step == "severity":
        return severity_known_on_episode(ep)
    if step == "current":
        return current_known_on_episode(ep)
    if step == "associated":
        # Mentions alone do not satisfy — must still clarify once unless answered.
        val = _attr(ep, "associated")
        if _meaningful(val) and val != "already_mentioned":
            return True
        return False
    return _meaningful(_attr(ep, step))
