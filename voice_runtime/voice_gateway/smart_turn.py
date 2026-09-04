"""Pipecat Smart Turn placeholder — env-gated endpointing (Phase 6)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def smart_turn_enabled() -> bool:
    raw = os.environ.get("MOSS_SMART_TURN", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


@dataclass
class SmartTurnResult:
    complete: bool
    confidence: float = 0.0
    source: str = "silero_vad"


class SmartTurnAnalyzer:
    """Optional Smart Turn model wrapper.

    When ``MOSS_SMART_TURN=1`` and the optional dependency is installed,
    ``analyze()`` may refine VAD endpointing. Otherwise falls back to the
    Silero VAD turn boundary supplied by ``GatewayVadBridge``.
    """

    def __init__(self) -> None:
        self._model = None
        self._load_error = ""
        if smart_turn_enabled():
            self._try_load()

    def _try_load(self) -> None:
        try:
            import importlib
            self._model = importlib.import_module("pipecat")  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            self._load_error = str(exc)
            self._model = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def analyze(
        self,
        pcm_samples: list[int],
        *,
        vad_complete: bool,
    ) -> SmartTurnResult:
        if not smart_turn_enabled() or not self.ready:
            return SmartTurnResult(complete=vad_complete, source="silero_vad")
        # Future: call Smart Turn model on pcm_samples; for now honour VAD.
        return SmartTurnResult(
            complete=vad_complete,
            confidence=0.85 if vad_complete else 0.2,
            source="smart_turn_stub",
        )
