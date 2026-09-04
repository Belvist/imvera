"""Continuous PCM ingress session — trace + endpoint (Track B, Wave RT-1)."""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from voice_runtime.ingress_trace import IngressTrace
from voice_runtime.turn_detector import TunedEndpointPolicy, TurnDecision
from voice_runtime.vad import ENERGY_THRESHOLD, SAMPLE_RATE, rms
from voice_runtime.voice_gateway.vad_bridge import GatewayVadBridge

_CHUNK_MS = 30.0
_SAMPLES_PER_CHUNK = int(SAMPLE_RATE * _CHUNK_MS / 1000)


@dataclass
class IngressTurn:
    call_id: str
    samples: list[int]
    sample_count: int
    endpoint: TurnDecision
    trace: IngressTrace
    generation_id: int = 0


@dataclass
class GatewayIngressSession:
    """One call's continuous PCM path — frames traced before turn commit."""

    call_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    generation_id: int = 0
    trace: IngressTrace = field(default_factory=IngressTrace)
    turn_detector: TunedEndpointPolicy = field(default_factory=TunedEndpointPolicy)
    on_turn: Callable[[IngressTurn], None] | None = None

    _sequence: int = 0
    _speech_active: bool = False
    _speech_started: bool = False
    _silence_ms: float = 0.0
    _speech_ms: float = 0.0
    _turn_buffer: list[int] = field(default_factory=list)
    _vad: GatewayVadBridge = field(default_factory=GatewayVadBridge)

    def __post_init__(self) -> None:
        self.trace.call_id = self.call_id
        self.trace.generation_id = self.generation_id

    def feed_pcm(
        self,
        data: bytes,
        *,
        agent_speaking: bool = False,
    ) -> dict[str, Any]:
        """Ingest one PCM frame; return events + optional committed turn."""
        if len(data) < 2:
            return {"events": [], "turn": None}

        count = len(data) // 2
        samples = list(struct.unpack("<" + "h" * count, data[: count * 2]))
        frame_ms = 1000.0 * len(samples) / SAMPLE_RATE
        energy = rms(samples)
        self._sequence += 1

        was_active = self._speech_active
        if energy >= ENERGY_THRESHOLD:
            self._speech_active = True
            self._silence_ms = 0.0
            self._speech_ms += frame_ms
            self._turn_buffer.extend(samples)
            if not was_active:
                self._speech_started = True
                self.trace.speech_start()
        else:
            self._speech_active = False
            self._silence_ms += frame_ms
            if self._speech_started and self._turn_buffer:
                self._turn_buffer.extend(samples)

        self.trace.pcm_frame(
            sequence=self._sequence,
            nbytes=len(data),
            rms=energy,
            speech_active=self._speech_active,
        )

        events: list[dict[str, Any]] = []
        for ev in self._vad.feed_pcm(samples, agent_speaking=agent_speaking):
            events.append(ev)
            if ev["type"] == "speech_onset" and agent_speaking:
                events.append(
                    {
                        "type": "cancel",
                        "generation_id": self.generation_id,
                        "reason": "barge_in",
                    }
                )

        turn_out: IngressTurn | None = None
        decision = self.turn_detector.is_complete(
            speech_active=self._speech_active,
            silence_ms=self._silence_ms,
            speech_ms=self._speech_ms,
            vad_turn_ready=self._speech_started and self._speech_ms > 0,
        )
        if decision.complete and self._turn_buffer:
            self.trace.speech_end()
            self.trace.endpoint_decision(
                source=decision.source,
                silence_ms=decision.silence_ms,
            )
            committed = list(self._turn_buffer)
            self.trace.turn_committed(sample_count=len(committed))
            turn_out = IngressTurn(
                call_id=self.call_id,
                samples=committed,
                sample_count=len(committed),
                endpoint=decision,
                trace=self.trace,
                generation_id=self.generation_id,
            )
            if self.on_turn:
                self.on_turn(turn_out)
            self._reset_turn_state()

        return {
            "events": events,
            "turn": turn_out,
            "sequence": self._sequence,
            "speech_active": self._speech_active,
            "silence_ms": self._silence_ms,
            "speech_ms": self._speech_ms,
        }

    def _reset_turn_state(self) -> None:
        self._turn_buffer = []
        self._speech_active = False
        self._speech_started = False
        self._silence_ms = 0.0
        self._speech_ms = 0.0

    def prove_status(self) -> dict[str, Any]:
        proof = self.trace.prove_continuous_ingress()
        return {
            "status": "STREAMING_INGRESS_PROVEN" if proof["ok"] else "STREAMING_INGRESS_PENDING",
            "call_id": self.call_id,
            "proof": proof,
            "trace": self.trace.to_dict(),
        }
