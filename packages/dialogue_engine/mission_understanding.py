"""Mission understanding boundary — candidates only, no EngineState writes.

Production semantic model plugs in via MissionUnderstandingProvider.
Slice 1 default: FastPath only for bare да/нет/не знаю to a DELIVERED goal.
Domain/mission-specific regex dictionaries are forbidden here.
"""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel

from packages.contracts.semantic import IssueMention
from packages.dialogue_engine.mission import CallMission, GoalAnswerCandidate
from packages.dialogue_engine.semantic_kernel.types import Observation

# Bare polarity only — no domain / mission verb dictionaries.
# Refusal phrases ("не хочу" / "не надо") are NOT factual "no".
_BARE_YES = re.compile(r"(?i)^\s*(да|ага|угу)\s*[.!]?\s*$")
_BARE_NO = re.compile(r"(?i)^\s*(нет)\s*[.!]?\s*$")
_BARE_UNKNOWN = re.compile(r"(?i)^\s*(не\s+знаю|не\s+помню)\s*[.!]?\s*$")


class MissionUnderstandingRequest(BaseModel):
    text: str
    utterance_id: str
    mission: CallMission
    active_goal_id: str | None = None
    delivered_question_text: str | None = None

    model_config = {"frozen": True}


class StructuredMissionResult(BaseModel):
    """Schema shared by fake test providers and future production semantic model."""

    goal_answers: tuple[GoalAnswerCandidate, ...] = ()
    observations: tuple[Observation, ...] = ()
    issue_mentions: tuple[IssueMention, ...] = ()
    user_question: str | None = None
    control: str = "none"

    model_config = {"frozen": True}


class MissionUnderstandingProvider(Protocol):
    def understand(self, request: MissionUnderstandingRequest) -> StructuredMissionResult:
        """Return structured candidates. Must not mutate EngineState."""


class FastPathMissionProvider:
    """Universal contextual answers only: bare yes/no/unknown → DELIVERED goal."""

    def understand(self, request: MissionUnderstandingRequest) -> StructuredMissionResult:
        text = (request.text or "").strip()
        if not text or not request.active_goal_id:
            return StructuredMissionResult()
        gdef = next(
            (g for g in request.mission.goals if g.goal_id == request.active_goal_id),
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
                    goal_id=request.active_goal_id,
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
    """Install provider for process (tests / future production wiring)."""
    global _provider
    _provider = provider


def get_mission_understanding_provider() -> MissionUnderstandingProvider:
    return _provider if _provider is not None else FastPathMissionProvider()


def understand_mission(
    request: MissionUnderstandingRequest,
    *,
    provider: MissionUnderstandingProvider | None = None,
) -> StructuredMissionResult:
    """Run provider. Never writes EngineState. May return multiple goal_answers."""
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
