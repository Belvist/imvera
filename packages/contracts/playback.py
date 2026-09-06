"""Playback accounting — generated vs heard."""

from datetime import datetime

from pydantic import BaseModel


class PlaybackPhrase(BaseModel):
    phrase_id: str
    generation_id: str
    turn_id: int
    generated_text: str
    tts_pcm_created_at: datetime | None = None
    playback_started_at: datetime | None = None
    playback_stopped_at: datetime | None = None
    played_samples: int = 0
    sample_rate: int = 8000
    interrupted: bool = False
    heard_text_estimate: str | None = None
