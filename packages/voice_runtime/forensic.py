"""Per-turn forensic helpers — echo similarity and turn-boundary classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from packages.voice_perception.text_echo import (
    is_text_echo_of_bot,
    normalize_speech_text,
    text_echo_similarity,
)

__all__ = [
    "ForensicTurnSnapshot",
    "classify_turn",
    "is_text_echo_of_bot",
    "normalize_speech_text",
    "text_echo_similarity",
    "utc_now_iso",
]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ForensicTurnSnapshot:
    utterance_id: str
    bot_playout_end_ts: str | None
    listen_open_ts: str | None
    vad_speech_start_ts: str | None
    vad_speech_end_ts: str | None
    stt_audio_start_ts: str | None
    stt_audio_end_ts: str | None
    stt_rms: float
    stt_duration_ms: int
    stt_latency_ms: int
    last_bot_text: str
    stt_text: str
    echo_similarity: float
    echo_score_max: float
    delivered_slot: str
    interpret_path: str
    interpret_latency_ms: int
    dump_path: str
    # Live-diagnosis fields (fs-9a5cfc31 class: traced inputs clean, answer
    # wrong — the adjudicated picture must be visible, not reconstructed).
    interp_judgement: str = ""
    interp_act: str = ""
    interp_fills_pending: str = ""
    rich_facts: str = ""
    rich_mentions: str = ""
    kernel_confidence: str = ""
    answer_slot: str = ""

    def as_payload(self) -> dict[str, object]:
        return {
            "utterance_id": self.utterance_id,
            "bot_playout_end_ts": self.bot_playout_end_ts or "",
            "listen_open_ts": self.listen_open_ts or "",
            "vad_speech_start_ts": self.vad_speech_start_ts or "",
            "vad_speech_end_ts": self.vad_speech_end_ts or "",
            "stt_audio_start_ts": self.stt_audio_start_ts or "",
            "stt_audio_end_ts": self.stt_audio_end_ts or "",
            "stt_rms": self.stt_rms,
            "stt_duration_ms": self.stt_duration_ms,
            "stt_latency_ms": self.stt_latency_ms,
            "last_bot_text": self.last_bot_text,
            "stt_text": self.stt_text,
            "echo_similarity": self.echo_similarity,
            "echo_score_max": self.echo_score_max,
            "delivered_slot": self.delivered_slot,
            "interpret_path": self.interpret_path,
            "interpret_latency_ms": self.interpret_latency_ms,
            "dump_path": self.dump_path,
            "interp_judgement": self.interp_judgement,
            "interp_act": self.interp_act,
            "interp_fills_pending": self.interp_fills_pending,
            "rich_facts": self.rich_facts,
            "rich_mentions": self.rich_mentions,
            "kernel_confidence": self.kernel_confidence,
            "answer_slot": self.answer_slot,
        }


def classify_turn(
    *,
    echo_similarity: float,
    echo_score_max: float,
    interpret_path: str,
    interpret_latency_ms: int,
    stt_text: str,
    expected_text: str | None = None,
) -> str:
    """Classify a user turn for forensic gate reporting."""
    if interpret_path == "echo_discarded":
        return "CAPTURE_ECHO"
    if echo_score_max >= 0.85:
        return "CAPTURE_ECHO"
    if expected_text:
        exp = normalize_speech_text(expected_text)
        got = normalize_speech_text(stt_text)
        if exp and got and exp != got:
            if exp not in got and got not in exp:
                return "STT_ERROR"
    if interpret_path in {"llm", "llm_fallback", "rules_fallback"} and interpret_latency_ms >= 2000:
        return "INTERPRETER_SLOW_PATH"
    if interpret_path in {"fast_contextual", "fast_rules"}:
        return "FAST_PATH"
    if interpret_path == "echo_discarded":
        return "CAPTURE_ECHO"
    return "OK"
