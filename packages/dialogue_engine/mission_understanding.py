"""Mission understanding boundary — candidates only, no EngineState writes.

Production default: DeterministicMissionUnderstandingProvider (CallMission data +
context). FastPathMissionProvider remains for bare-polarity unit tests / DI.
Domain/mission-specific regex dictionaries are forbidden here.
"""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel

from packages.contracts.semantic import IssueMention
from packages.dialogue_engine.mission import CallMission, GoalAnswerCandidate, GoalDispositionCandidate
from packages.dialogue_engine.semantic_kernel.types import Observation


# Bare polarity only — no domain / mission verb dictionaries.
# Refusal phrases ("не хочу" / "не надо") are NOT factual "no".
_BARE_YES = re.compile(r"(?i)^\s*(да|ага|угу)\s*[.!]?\s*$")
_BARE_NO = re.compile(r"(?i)^\s*(нет)\s*[.!]?\s*$")
_BARE_UNKNOWN = re.compile(r"(?i)^\s*(не\s+знаю|не\s+помню)\s*[.!]?\s*$")


class MissionUnderstandingContext(BaseModel):
    """Read-only projection for understanding — not a state store."""

    mission_id: str = ""
    goal_ids: tuple[str, ...] = ()
    goal_lifecycles: tuple[tuple[str, str], ...] = ()
    grounded_answers: tuple[tuple[str, str, str], ...] = ()  # id, value, evidence
    delivered_goal_id: str | None = None
    delivered_question_text: str | None = None
    delivered_question_phase: str | None = None
    suspended_goal_id: str | None = None
    open_episode_summaries: tuple[str, ...] = ()

    model_config = {"frozen": True}


class MissionUnderstandingRequest(BaseModel):
    text: str
    utterance_id: str
    mission: CallMission
    active_goal_id: str | None = None
    delivered_question_text: str | None = None
    delivered_goal_id: str | None = None
    delivered_question_phase: str | None = None
    context: MissionUnderstandingContext | None = None

    model_config = {"frozen": True}


class StructuredMissionResult(BaseModel):
    """Schema shared by fake test providers and production semantic model."""

    goal_answers: tuple[GoalAnswerCandidate, ...] = ()
    goal_dispositions: tuple[GoalDispositionCandidate, ...] = ()
    observations: tuple[Observation, ...] = ()
    issue_mentions: tuple[IssueMention, ...] = ()
    user_question: str | None = None
    control: str = "none"

    model_config = {"frozen": True}


class MissionUnderstandingProvider(Protocol):
    def understand(self, request: MissionUnderstandingRequest) -> StructuredMissionResult:
        """Return structured candidates. Must not mutate EngineState."""


class FastPathMissionProvider:
    """Bare yes/no/unknown only — and only for a really DELIVERED goal question."""

    def understand(self, request: MissionUnderstandingRequest) -> StructuredMissionResult:
        text = (request.text or "").strip()
        goal_id = request.delivered_goal_id or request.active_goal_id
        if not text or not goal_id:
            return StructuredMissionResult()
        phase = (request.delivered_question_phase or "").upper()
        if phase and phase != "DELIVERED":
            return StructuredMissionResult()
        if request.context is not None:
            if request.context.delivered_goal_id != goal_id:
                return StructuredMissionResult()
            if (request.context.delivered_question_phase or "").upper() != "DELIVERED":
                return StructuredMissionResult()
        elif not request.delivered_goal_id:
            # Without explicit delivered goal, refuse fast-path binding.
            return StructuredMissionResult()
        gdef = next(
            (g for g in request.mission.goals if g.goal_id == goal_id),
            None,
        )
        if gdef is None or gdef.answer_type not in {"enum", "bool"}:
            return StructuredMissionResult()
        allowed = set(gdef.allowed_values) or {"yes", "no", "unknown"}
        value: str | None = None
        evidence = ""
        if _BARE_YES.match(text):
            value, evidence = "yes", text.strip()
        elif _BARE_NO.match(text):
            value, evidence = "no", text.strip()
        elif _BARE_UNKNOWN.match(text):
            value, evidence = "unknown", text.strip()
        if value is None or value not in allowed:
            return StructuredMissionResult()
        return StructuredMissionResult(
            goal_answers=(
                GoalAnswerCandidate(
                    goal_id=goal_id,
                    value=value,
                    confidence=0.95,
                    evidence=evidence,
                ),
            )
        )


_provider: MissionUnderstandingProvider | None = None


def set_mission_understanding_provider(
    provider: MissionUnderstandingProvider | None,
) -> None:
    """Test/process hook only — production DI is CallSession/DialogueEngine provider arg."""
    global _provider
    _provider = provider


def get_mission_understanding_provider() -> MissionUnderstandingProvider:
    """Production default: deterministic mission understanding (no LLM)."""
    if _provider is not None:
        return _provider
    from packages.dialogue_engine.deterministic_mission import (
        DeterministicMissionUnderstandingProvider,
    )

    return DeterministicMissionUnderstandingProvider()


def understand_mission(
    request: MissionUnderstandingRequest,
    *,
    provider: MissionUnderstandingProvider | None = None,
) -> StructuredMissionResult:
    """Run provider. Never writes EngineState. May return multiple goal_answers.

    Prefer explicit ``provider`` from CallSession/DialogueEngine. Process-global
    ``_provider`` is a temporary test hook, not production DI.
    """
    active = provider if provider is not None else get_mission_understanding_provider()
    result = active.understand(request)
    # Defensive: drop empty / incomplete candidates at boundary (engine still validates).
    answers = tuple(
        a
        for a in result.goal_answers
        if a.goal_id and a.value is not None and str(a.value).strip() != ""
    )
    return result.model_copy(update={"goal_answers": answers})


def reset_mission_understanding_provider() -> None:
    set_mission_understanding_provider(None)
