"""CallMission input for DialogueEngine — not a separate runtime.

GoalDefinition = immutable mission catalog entry.
Runtime progress lives on EngineState.goals (GoalState).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GoalDefinition(BaseModel):
    """Immutable description of what the app asked Vera to learn."""

    goal_id: str
    kind: str = "collect_fact"
    description: str = ""
    prompt_hint: str = ""
    required: bool = True
    priority: int = 100
    answer_type: Literal["enum", "free_text", "bool"] = "enum"
    allowed_values: tuple[str, ...] = ("yes", "no", "unknown")
    max_attempts: int = 2
    source: str = "mission"

    model_config = {"frozen": True}


class CallMission(BaseModel):
    """App-assigned call purpose. DialogueEngine is the only runtime owner."""

    mission_id: str
    goals: tuple[GoalDefinition, ...] = ()
    preset: str | None = None  # "daily_check" when using compatibility preset

    model_config = {"frozen": True}

    @property
    def is_daily_check(self) -> bool:
        return self.preset == "daily_check"

    @property
    def is_custom(self) -> bool:
        return not self.is_daily_check


_DAILY_CHECK_HINTS: dict[str, str] = {
    "wellness": "Как вы себя чувствуете?",
    "mood": "Как настроение?",
    "sleep": "Как спали?",
    "plans": "Какие планы на день?",
}


def daily_check_mission() -> CallMission:
    """Compatibility preset — four classic slots as ordinary GoalDefinitions."""
    goals = tuple(
        GoalDefinition(
            goal_id=slot,
            kind="collect_fact",
            description=f"Daily check: {slot}",
            prompt_hint=_DAILY_CHECK_HINTS[slot],
            required=True,
            priority=10 + i,
            answer_type="free_text",
            allowed_values=(),
            source="daily_check_preset",
        )
        for i, slot in enumerate(("wellness", "mood", "sleep", "plans"))
    )
    return CallMission(mission_id="daily_check", goals=goals, preset="daily_check")


def definition_by_id(mission: CallMission, goal_id: str) -> GoalDefinition | None:
    for item in mission.goals:
        if item.goal_id == goal_id:
            return item
    return None


class GoalAnswerCandidate(BaseModel):
    """Structured understanding output — never writes EngineState by itself."""

    goal_id: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""
    is_correction: bool = False

    model_config = {"frozen": True}


class GoalDispositionCandidate(BaseModel):
    """User declines / N/A / unclear about a goal — not a factual yes/no answer."""

    goal_id: str
    disposition: Literal["declined", "not_applicable", "unclear"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""

    model_config = {"frozen": True}


class CustomMissionRequiresDialogueEngine(RuntimeError):
    """Custom CallMission must not silently fall back to legacy Planner."""
