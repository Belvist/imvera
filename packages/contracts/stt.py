"""STT contracts — do not use raw Whisper confidence as product truth."""

from pydantic import BaseModel, Field

from packages.contracts.enums import AsrQuality


class CriticalTermMatch(BaseModel):
    term: str
    matched: bool
    logprob: float | None = None


class AudioQualityHints(BaseModel):
    rms: float | None = None
    snr_estimate: float | None = None


class STTPartial(BaseModel):
    text: str = ""
    partial_id: str
    is_final: bool = False
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


class STTResult(BaseModel):
    text: str
    is_final: bool = True
    partial_id: str | None = None
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    word_probs: list[float] = Field(default_factory=list)
    audio_quality: AudioQualityHints = Field(default_factory=AudioQualityHints)
    critical_terms: list[CriticalTermMatch] = Field(default_factory=list)
    asr_quality: AsrQuality = AsrQuality.GOOD
    # Observability — raw GigaAM output before normalize (trace stt.result).
    raw_text: str | None = None
    duration_ms: int | None = None
    model_revision: str | None = None
