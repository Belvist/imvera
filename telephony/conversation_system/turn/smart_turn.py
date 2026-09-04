"""Smart Turn endpointing interface stub (P1 scaffold).

Future: ML-based turn boundary detection replacing fixed silence caps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TurnBoundarySignal:
    """Hint from smart-turn model whether the caller finished speaking."""

    end_of_turn: bool
    confidence: float = 0.0
    reason: str = ""


@runtime_checkable
class SmartTurnProvider(Protocol):
    """Pluggable smart-turn backend (GigaAM / Silero endpointing / custom)."""

    def ready(self) -> bool:
        ...

    def evaluate_pcm(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int = 16000,
    ) -> TurnBoundarySignal:
        ...


class NullSmartTurn:
    """Fail-open: never signals end-of-turn (legacy silence caps remain)."""

    def ready(self) -> bool:
        return True

    def evaluate_pcm(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int = 16000,
    ) -> TurnBoundarySignal:
        return TurnBoundarySignal(end_of_turn=False, confidence=0.0, reason="null")
