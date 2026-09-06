"""Runtime events, task ids, and side-effect results for VoiceRuntime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RuntimeEventType(StrEnum):
    CALL_STARTED = "call.started"
    MEDIA_READY = "media.ready"
    SPEECH_STARTED = "speech.started"
    SPEECH_ENDED = "speech.ended"
    STT_PARTIAL = "stt.partial"
    STT_FINAL = "stt.final"
    INTERPRETATION_READY = "interpretation.ready"
    INTERPRETATION_FAILED = "interpretation.failed"
    PERSISTENCE_COMMITTED = "persistence.committed"
    PERSISTENCE_FAILED = "persistence.failed"
    CORE_ACCEPTED = "core.accepted"
    RENDERER_PHRASE_READY = "renderer.phrase_ready"
    TTS_CHUNK_READY = "tts.chunk_ready"
    PLAYBACK_STARTED = "playback.started"
    PLAYBACK_PROGRESS = "playback.progress"
    PLAYBACK_COMPLETED = "playback.completed"
    PLAYBACK_INTERRUPTED = "playback.interrupted"
    CONSENT_CHANGED = "consent.changed"
    TRANSPORT_DISCONNECTED = "transport.disconnected"
    CALL_STOP_REQUESTED = "call.stop_requested"
    PROVIDER_TIMEOUT = "provider.timeout"
    CALL_DEADLINE_REACHED = "call.deadline_reached"


@dataclass(frozen=True)
class RuntimeEvent:
    call_id: str
    event_type: RuntimeEventType
    payload: dict[str, Any] = field(default_factory=dict)
    monotonic_ts: float = 0.0


@dataclass(frozen=True)
class TaskRef:
    """Correlation for async work tied to one call."""

    call_id: str
    task_kind: str
    task_id: str
    utterance_id: str | None = None
    generation_id: str | None = None


@dataclass(frozen=True)
class SideEffectResult:
    ok: bool
    task: TaskRef
    error: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
