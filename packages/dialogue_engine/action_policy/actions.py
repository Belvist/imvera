"""Closed, parameterized dialogue-action catalog for offline policy evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from packages.dialogue_engine.question_context import QuestionNeed


class ActionKind(StrEnum):
    ASK_EPISODE = "ASK_EPISODE"
    ACK_ONLY = "ACK_ONLY"
    CLARIFY = "CLARIFY"
    ANSWER_USER = "ANSWER_USER"
    IMPORTANT_TO_SHARE = "IMPORTANT_TO_SHARE"
    BACKGROUND_GOAL = "BACKGROUND_GOAL"
    REPAIR = "REPAIR"
    CONTROL = "CONTROL"
    SAFETY = "SAFETY"
    SUMMARY_CLOSE = "SUMMARY_CLOSE"
    GOODBYE_FINAL = "GOODBYE_FINAL"
    LISTEN_META = "LISTEN_META"


def normalize_need(need: QuestionNeed | None) -> str | None:
    if need is None:
        return None
    normalized: list[str] = []
    for attr in need.attributes:
        if attr in ("onset", "duration", "temporal"):
            key = "temporal"
        elif attr in ("current", "status"):
            key = "current"
        else:
            key = attr
        if key not in normalized:
            normalized.append(key)
    return "+".join(sorted(normalized)) if normalized else None


@dataclass(frozen=True, order=True)
class ActionKey:
    """Comparison key intentionally excludes dynamic episode IDs."""

    kind: ActionKind
    need: str | None = None
    target_goal: str | None = None
    control: str | None = None
    clarify_target: str | None = None

    def label(self) -> str:
        parts = [self.kind.value]
        if self.need:
            parts.append(self.need)
        if self.target_goal:
            parts.append(self.target_goal)
        if self.control:
            parts.append(self.control)
        if self.clarify_target:
            parts.append(self.clarify_target)
        return ":".join(parts)


@dataclass(frozen=True)
class CandidateAction:
    kind: ActionKind
    episode_id: str | None = None
    question_need: QuestionNeed | None = None
    target_goal: str | None = None
    control: str | None = None
    clarify_target: str | None = None

    @property
    def key(self) -> ActionKey:
        return ActionKey(
            kind=self.kind,
            need=normalize_need(self.question_need),
            target_goal=self.target_goal,
            control=self.control,
            clarify_target=self.clarify_target,
        )


@dataclass(frozen=True)
class ConstraintRejection:
    action: CandidateAction
    rule_id: str
    reason: str


@dataclass(frozen=True)
class ScoredAction:
    action: CandidateAction
    score: float
    features: dict[str, float] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDecision:
    chosen: CandidateAction
    candidates: tuple[ScoredAction, ...]
    rejected: tuple[ConstraintRejection, ...]
    policy_version: str


class PolicyConstraintViolation(Exception):
    """Raised when hard constraints eliminate every candidate for the mandatory class."""

    def __init__(
        self,
        *,
        mandatory_class: str,
        rejected: tuple[ConstraintRejection, ...] = (),
        message: str = "no valid candidates for mandatory class",
    ) -> None:
        self.mandatory_class = mandatory_class
        self.rejected = rejected
        super().__init__(message)
