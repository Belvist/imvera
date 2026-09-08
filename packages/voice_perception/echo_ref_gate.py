"""Reference-based echo gate — always-listen without hearing Vera as the user.

We already know the downlink PCM we inject. Keep a short ring of that audio and
compare uplink frames against it (normalized cross-correlation + energy). Frames
that match recent playback are treated as acoustic echo and must not enter VAD.

This is NOT ML speaker-ID (X-vector). It is lab AEC/gating from a known reference.
True WebRTC AEC / speaker embeddings are a later upgrade.
"""

from __future__ import annotations

import array
import math
import os
from dataclasses import dataclass
from enum import StrEnum


class EchoVerdict(StrEnum):
    ECHO = "echo"
    USER = "user"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class EchoRefConfig:
    """Tuning for reference echo classification (PCM16 mono)."""

    sample_rate: int = 16000
    ref_ms: int = 1500
    max_lag_ms: int = 400
    lag_stride_ms: int = 5
    ncc_echo: float = 0.72
    ncc_user: float = 0.45
    silence_rms: float = 80.0
    energy_match_db: float = 14.0


def echo_ref_gate_enabled() -> bool:
    """IMVERA_ECHO_REF_GATE — default off; pair with always-listen (HALF_DUPLEX=0)."""
    return os.environ.get("IMVERA_ECHO_REF_GATE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def lab_barge_in_enabled() -> bool:
    """IMVERA_LAB_BARGE_IN — interrupt Vera on clear user speech (default off)."""
    return os.environ.get("IMVERA_LAB_BARGE_IN", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def apply_echo_ref_env(env: dict[str, str]) -> dict[str, str]:
    """Opt-in echo-ref defaults — does not flip half-duplex off by itself."""
    env.setdefault("IMVERA_ECHO_REF_GATE", "0")
    env.setdefault("IMVERA_LAB_BARGE_IN", "0")
    return env


class DownlinkEchoRef:
    """Ring buffer of recently played downlink PCM + uplink echo classifier."""

    def __init__(self, config: EchoRefConfig | None = None) -> None:
        self.config = config or EchoRefConfig()
        self._max_samples = max(
            1, int(self.config.sample_rate * self.config.ref_ms / 1000)
        )
        self._samples = array.array("h")
        self._frame_samples = max(1, self.config.sample_rate * 20 // 1000)
        self._lag_stride = max(
            1, int(self.config.sample_rate * self.config.lag_stride_ms / 1000)
        )
        self._max_lag = max(
            0, int(self.config.sample_rate * self.config.max_lag_ms / 1000)
        )

    def clear(self) -> None:
        self._samples = array.array("h")

    def push(self, pcm_s16le: bytes) -> None:
        """Append PCM that was just injected toward the softphone/PSTN."""
        if not pcm_s16le:
            return
        n = len(pcm_s16le) - (len(pcm_s16le) % 2)
        if n <= 0:
            return
        chunk = array.array("h")
        chunk.frombytes(pcm_s16le[:n])
        self._samples.extend(chunk)
        overflow = len(self._samples) - self._max_samples
        if overflow > 0:
            del self._samples[:overflow]

    @property
    def buffered_samples(self) -> int:
        return len(self._samples)

    def classify(self, uplink_pcm: bytes, *, playback_active: bool) -> EchoVerdict:
        """Compare one uplink frame against recent downlink reference."""
        up = self._as_samples(uplink_pcm)
        if not up:
            return EchoVerdict.UNCERTAIN

        up_energy = self._energy(up)
        up_rms = math.sqrt(up_energy / len(up)) if up else 0.0
        if up_rms < self.config.silence_rms:
            return EchoVerdict.USER

        if len(self._samples) < len(up):
            if playback_active:
                return EchoVerdict.UNCERTAIN
            return EchoVerdict.USER

        best_ncc = -1.0
        best_ref_energy = 0.0
        n = len(up)
        latest_start = len(self._samples) - n
        earliest_start = max(0, latest_start - self._max_lag)
        for start in range(latest_start, earliest_start - 1, -self._lag_stride):
            window = self._samples[start : start + n]
            if len(window) < n:
                continue
            ref_energy = self._energy(window)
            if ref_energy < 1.0:
                continue
            ncc = self._ncc(up, window, up_energy, ref_energy)
            if ncc > best_ncc:
                best_ncc = ncc
                best_ref_energy = ref_energy

        if best_ncc < 0.0:
            if playback_active:
                return EchoVerdict.UNCERTAIN
            return EchoVerdict.USER

        energy_ok = self._energy_match(up_energy, best_ref_energy)
        if best_ncc >= self.config.ncc_echo and energy_ok:
            return EchoVerdict.ECHO
        if best_ncc <= self.config.ncc_user:
            return EchoVerdict.USER
        if playback_active:
            return EchoVerdict.UNCERTAIN
        return EchoVerdict.USER

    def should_drop_for_vad(self, uplink_pcm: bytes, *, playback_active: bool) -> bool:
        """True → do not feed VAD (echo or fail-safe uncertain while Vera plays)."""
        verdict = self.classify(uplink_pcm, playback_active=playback_active)
        if verdict == EchoVerdict.ECHO:
            return True
        if verdict == EchoVerdict.UNCERTAIN and playback_active:
            return True
        return False

    @staticmethod
    def _as_samples(pcm: bytes) -> array.array:
        n = len(pcm) - (len(pcm) % 2)
        out = array.array("h")
        if n > 0:
            out.frombytes(pcm[:n])
        return out

    @staticmethod
    def _energy(samples: array.array) -> float:
        return float(sum(int(s) * int(s) for s in samples))

    @staticmethod
    def _ncc(
        a: array.array, b: array.array, energy_a: float, energy_b: float
    ) -> float:
        if len(a) != len(b) or energy_a <= 0.0 or energy_b <= 0.0:
            return -1.0
        dot = float(sum(int(x) * int(y) for x, y in zip(a, b)))
        denom = math.sqrt(energy_a * energy_b)
        if denom <= 0.0:
            return -1.0
        return dot / denom

    def _energy_match(self, up_energy: float, ref_energy: float) -> bool:
        if up_energy <= 0.0 or ref_energy <= 0.0:
            return False
        ratio = up_energy / ref_energy
        db = abs(10.0 * math.log10(ratio))
        return db <= self.config.energy_match_db
