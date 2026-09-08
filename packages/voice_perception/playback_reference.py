"""Playback reference for delay-aware echo classification (L1 audio guard)."""

from __future__ import annotations

from dataclasses import dataclass

from packages.voice_perception.echo_ref_gate import (
    DownlinkEchoRef,
    EchoRefConfig,
    EchoVerdict,
)


@dataclass(frozen=True)
class EchoClassification:
    verdict: EchoVerdict
    score: float
    playback_active: bool

    @property
    def is_echo(self) -> bool:
        return self.verdict == EchoVerdict.ECHO

    @property
    def is_user(self) -> bool:
        return self.verdict == EchoVerdict.USER


class PlaybackReference:
    """Known downlink PCM + uplink echo classifier."""

    def __init__(self, config: EchoRefConfig | None = None) -> None:
        self._ref = DownlinkEchoRef(config)

    def clear(self) -> None:
        self._ref.clear()

    def push(self, pcm_s16le: bytes) -> None:
        self._ref.push(pcm_s16le)

    @property
    def buffered_samples(self) -> int:
        return self._ref.buffered_samples

    def classify(self, uplink_pcm: bytes, *, playback_active: bool) -> EchoClassification:
        verdict = self._ref.classify(uplink_pcm, playback_active=playback_active)
        score = self._estimate_score(uplink_pcm, verdict)
        return EchoClassification(
            verdict=verdict,
            score=score,
            playback_active=playback_active,
        )

    def should_gate_from_vad(self, uplink_pcm: bytes, *, playback_active: bool) -> bool:
        return self._ref.should_drop_for_vad(uplink_pcm, playback_active=playback_active)

    def _estimate_score(self, uplink_pcm: bytes, verdict: EchoVerdict) -> float:
        if verdict == EchoVerdict.ECHO:
            return 0.92
        if verdict == EchoVerdict.USER:
            return 0.12
        return 0.55
