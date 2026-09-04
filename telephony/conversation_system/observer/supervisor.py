"""Supervisor — post-observer invariant checks and LLM downgrade."""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from conversation_system.observer.observer import ObserverPatch
from conversation_system.reply.guards import _ACTION_PROMISE_RE

if TYPE_CHECKING:
    from conversation_system.domain.understanding import TurnUnderstanding
    from conversation_system.memory.state import ConversationMemory

_LOG = logging.getLogger(__name__)

_AGENDA_SKIP_MARKERS = (
    "следующ",
    "продолж",
    "перейд",
    "закрой тему",
    "следующую тему",
    "дальше по повестке",
)

_CORRECTION_MARKERS = (
    "не голова",
    "не спина",
    "имел в виду",
    "имела в виду",
    "не то",
    "исправ",
    "на самом деле",
)


class ObserverSupervisor:
    """Lightweight guard on observer output before resolver."""

    def review(
        self,
        patch: ObserverPatch,
        *,
        memory: "ConversationMemory",
        understanding: "TurnUnderstanding | None" = None,
        base_patch: ObserverPatch,
        llm_used: bool = False,
    ) -> ObserverPatch:
        overrides: list[str] = []
        directive = patch.next_directive
        corrections = patch.corrections
        contradictions = patch.contradictions
        memory_patches = list(patch.memory_patches)
        pending_invalid = patch.pending_invalid

        if directive and _ACTION_PROMISE_RE.search(directive):
            directive = base_patch.next_directive
            overrides.append("promise_phrase_in_directive")

        if pending_invalid and directive:
            low = directive.lower()
            if any(m in low for m in _AGENDA_SKIP_MARKERS):
                directive = base_patch.next_directive
                overrides.append("agenda_skip_on_invalid_choice")

        if llm_used and corrections and not base_patch.corrections:
            filtered = tuple(
                c for c in corrections if _looks_like_correction_text(c)
            )
            if not filtered:
                corrections = base_patch.corrections
                overrides.append("llm_correction_rejected")
            else:
                corrections = filtered

        if llm_used and contradictions and not base_patch.contradictions:
            if not _has_contradiction_signal(
                understanding.clean_text if understanding else ""
            ):
                contradictions = base_patch.contradictions
                overrides.append("llm_contradiction_rejected")

        if overrides:
            _LOG.info(
                "observer_supervisor_override call_id=%s reasons=%s",
                memory.call_id,
                ",".join(overrides),
            )

        return ObserverPatch(
            corrections=corrections,
            contradictions=contradictions,
            unanswered_user_questions=patch.unanswered_user_questions,
            next_directive=directive,
            memory_patches=tuple(memory_patches),
            pending_invalid=pending_invalid,
            llm_enriched=patch.llm_enriched and not overrides,
            supervisor_overrides=tuple(overrides),
        )


def _looks_like_correction_text(text: str) -> bool:
    low = (text or "").lower()
    if not low:
        return False
    return any(m in low for m in _CORRECTION_MARKERS)


def _has_contradiction_signal(text: str) -> bool:
    low = (text or "").lower()
    if not low:
        return False
    return bool(
        re.search(
            r"(на\s+самом\s+деле|вообще\s+то|нет\s*[,]?\s*наоборот)",
            low,
        )
    )
