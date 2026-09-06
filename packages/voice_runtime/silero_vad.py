"""Silero VAD via ONNX with energy fallback."""

from __future__ import annotations

from pathlib import Path

from packages.voice_runtime.vad import EnergyVad, VadConfig

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "config" / "models" / "silero_vad.onnx"


class SileroVad:
    """Streaming Silero VAD — 512-sample windows at 16 kHz."""

    def __init__(self, sample_rate: int = 16000, model_path: Path | None = None) -> None:
        if sample_rate != 16000:
            raise ValueError("Silero VAD adapter supports 16 kHz only")
        self.sample_rate = sample_rate
        self._window = 512
        self._min_speech_ms = 100
        self._min_silence_ms = 650
        self._frame_ms = 20
        import numpy as np
        import onnxruntime as ort

        path = model_path or DEFAULT_MODEL
        if not path.exists():
            raise FileNotFoundError(path)
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(path), providers=["CPUExecutionProvider"], sess_options=opts
        )
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)
        self._buf = b""
        self._in_speech = False
        self._speech_ms = 0
        self._silence_ms = 0

    def _probability(self, audio_f32) -> float:
        import numpy as np

        ort_inputs = {
            "input": audio_f32.reshape(1, -1),
            "h": self._h,
            "c": self._c,
            "sr": np.array(self.sample_rate, dtype=np.int64),
        }
        out, self._h, self._c = self._session.run(None, ort_inputs)
        return float(out[0][0])

    def feed(self, pcm: bytes) -> tuple[bool, bool]:
        import array

        started = False
        ended = False
        self._buf += pcm
        while len(self._buf) >= self._window * 2:
            frame = self._buf[: self._window * 2]
            self._buf = self._buf[self._window * 2 :]
            samples = array.array("h")
            samples.frombytes(frame)
            import numpy as np

            audio = np.array(samples, dtype=np.float32) / 32768.0
            prob = self._probability(audio)
            loud = prob >= 0.5
            if loud:
                self._silence_ms = 0
                self._speech_ms += self._frame_ms
                if not self._in_speech and self._speech_ms >= self._min_speech_ms:
                    self._in_speech = True
                    started = True
            elif self._in_speech:
                self._silence_ms += self._frame_ms
                if self._silence_ms >= self._min_silence_ms:
                    self._in_speech = False
                    self._speech_ms = 0
                    ended = True
            else:
                self._speech_ms = 0
        return started, ended

    @property
    def in_speech(self) -> bool:
        return self._in_speech


def create_vad(sample_rate: int, config: VadConfig | None = None) -> EnergyVad | SileroVad:
    try:
        return SileroVad(sample_rate)
    except (ImportError, FileNotFoundError, OSError, ValueError):
        return EnergyVad(sample_rate, config)
