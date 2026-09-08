"""Immutable engine decision — batch of effects from one reduce step."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.dialogue_engine.effects import Effect


@dataclass(frozen=True)
class Decision:
    revision: int
    effects: tuple[Effect, ...] = field(default_factory=tuple)

    @classmethod
    def from_effects(cls, revision: int, effects: list[Effect]) -> Decision:
        return cls(revision=revision, effects=tuple(effects))
