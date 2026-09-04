"""Turn completion policy — pluggable endpoint (Track B3)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TurnDecision:
    complete: bool
    source: str
    silence_ms: float = 0.0


class TurnDetector(Protocol):
    """Decides whether the user finished their turn (not raw VAD)."""

    def is_complete(
        self,
        *,
        speech_active: bool,
        silence_ms: float,
        speech_ms: float,
        vad_turn_ready: bool,
    ) -> TurnDecision:
        ...


class TunedEndpointPolicy:
    """Configurable silence endpoint — Smart Turn plugs in later."""

    def __init__(
        self,
        *,
        min_speech_ms: float | None = None,
        endpoint_silence_ms: float | None = None,
    ) -> None:
        self.min_speech_ms = float(
            min_speech_ms
            if min_speech_ms is not None
            else os.environ.get("MOSS_ENDPOINT_MIN_SPEECH_MS", "220")
        )
        self.endpoint_silence_ms = float(
            endpoint_silence_ms
            if endpoint_silence_ms is not None
            else os.environ.get("MOSS_ENDPOINT_SILENCE_MS", "700")
        )

    def is_complete(
        self,
        *,
        speech_active: bool,
        silence_ms: float,
        speech_ms: float,
        vad_turn_ready: bool,
    ) -> TurnDecision:
        if not vad_turn_ready:
            return TurnDecision(
                complete=False,
                source="vad_pending",
                silence_ms=silence_ms,
            )
        if speech_ms < self.min_speech_ms:
            return TurnDecision(
                complete=False,
                source="speech_too_short",
                silence_ms=silence_ms,
            )
        if silence_ms < self.endpoint_silence_ms:
            return TurnDecision(
                complete=False,
                source="silence_insufficient",
                silence_ms=silence_ms,
            )
        return TurnDecision(
            complete=True,
            source="tuned_endpoint",
            silence_ms=silence_ms,
        )
