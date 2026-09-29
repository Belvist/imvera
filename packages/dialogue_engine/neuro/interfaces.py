"""Neuro pipeline interfaces (ADR-024). Protocols only, no weights."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ParaphraseProposal:
    """One candidate surface for an already-fixed semantic contract."""

    text: str
    generator_version: str
    # Semantic signature the surface claims to realize (act + site +
    # polarity + preserved quotes). The checker verifies it, never trusts it.
    signature: str = ""


@dataclass(frozen=True)
class RankScores:
    """Scores over an EXPLICIT legal set. A model never emits action ids."""

    scores: dict[str, float] = field(default_factory=dict)
    ranker_version: str = ""
    legal_action_ids: tuple[str, ...] = ()


class SurfaceGenerator(Protocol):
    """Proposes surface variants for a fixed semantic contract."""

    version: str

    def propose(self, signature: str, canonical_text: str, n: int = 3) -> list[ParaphraseProposal]:
        ...


class SemanticChecker(Protocol):
    """Veto-only equivalence check. Abstention (None) is legal and common."""

    version: str

    def check(self, signature: str, proposed_text: str) -> bool | None:
        """True = equivalent, False = veto, None = abstain."""
        ...


class ActionRanker(Protocol):
    """Scores a fixed legal set. Abstention (empty scores) is legal."""

    version: str

    def score(
        self, features: dict[str, float], legal_action_ids: list[str]
    ) -> RankScores:
        ...
