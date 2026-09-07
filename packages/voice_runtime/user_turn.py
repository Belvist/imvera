"""User turn envelope — dialogue receives text, not raw WAV."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UserTurn:
    turn_id: int
    utterance_id: str
    pcm: bytes
    duration_ms: int
    pcm_rms: float
    echo_score: float = 0.0
    speech_ratio: float = 0.0
    pending_slot: str = ""
    question_at_start: str = ""
    raw_capture_path: str = ""
    processed_path: str = ""
    stt_input_path: str = ""
    playback_ref_path: str = ""
    text: str = ""
    stt_latency_ms: int = 0
    asr_quality: str = ""
    empty_reason: str = ""
    final: bool = True
    metadata: dict[str, object] = field(default_factory=dict)
