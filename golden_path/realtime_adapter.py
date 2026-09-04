"""Thin adapter: committed realtime turn → Golden Path engine (Track D)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from golden_path.engine import GoldenPathEngine, TurnResult
from golden_path.llm import LLMBackend


def golden_path_enabled() -> bool:
    return os.environ.get("VERA_GOLDEN_PATH", "").strip() in ("1", "true", "yes")


def legacy_fallback_enabled() -> bool:
    return os.environ.get("LEGACY_FALLBACK", "1").strip() not in ("0", "false", "no")


@dataclass(frozen=True)
class RealtimeTurn:
    """Committed user turn from VoiceGateway / ingress session."""

    call_id: str
    text: str
    generation_id: int = 0
    sample_count: int = 0
    endpoint_source: str = ""


class GoldenRealtimeAdapter:
    """RealtimeTurn → GoldenPathEngine.handle_turn (no legacy FSM)."""

    def __init__(
        self,
        llm: LLMBackend | None = None,
        *,
        trace_dir: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self._engine = GoldenPathEngine(
            llm=llm,
            trace_dir=trace_dir,
            session_id=session_id,
        )
        self._greeting_done = False

    @property
    def engine(self) -> GoldenPathEngine:
        return self._engine

    def begin_call(self, call_id: str) -> str:
        self._engine.session_id = call_id
        self._greeting_done = True
        return self._engine.begin_session()

    def handle_committed_turn(self, turn: RealtimeTurn) -> TurnResult:
        if not self._greeting_done:
            self.begin_call(turn.call_id)
        return self._engine.handle_turn(turn.text)

    def plan_committed_turn(self, turn: RealtimeTurn):
        return self._engine.plan_only(turn.text)
