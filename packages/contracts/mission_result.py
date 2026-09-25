"""Typed mission result for app / persistence — EngineState is canonical source."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GoalResultSnapshot(BaseModel):
    goal_id: str
    lifecycle: str
    value: str | None = None
    attempts: int = 0
    evidence: list[str] = Field(default_factory=list)
    required: bool = True


class MissionResultSnapshot(BaseModel):
    mission_id: str
    status: Literal["COMPLETED", "PARTIAL", "DECLINED", "NOT_RUN"] = "NOT_RUN"
    goals: list[GoalResultSnapshot] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    issue_summaries: list[str] = Field(default_factory=list)


class CallOutcomes(BaseModel):
    """Three product dimensions — not collapsed into one GREEN."""

    call_outcome: Literal["COMPLETED", "DECLINED", "NO_ANSWER", "TECHNICAL"] = "TECHNICAL"
    mission_status: Literal["COMPLETED", "PARTIAL", "DECLINED", "NOT_RUN"] = "NOT_RUN"
    candidate_family_status: Literal["GREEN", "YELLOW", "RED", "UNSET"] = "UNSET"
    """Candidate only — product-facing GREEN/RED requires Core ack (ADR-007)."""
