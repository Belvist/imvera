"""STT backend factory — explicit engine switch, no silent fallback."""

from __future__ import annotations

from typing import Any, Protocol


class AsrBackend(Protocol):
    def transcribe_wav(self, wav_path: Any, *, hotwords: list[str] | None = None) -> str:
        """Return raw transcript text for a mono WAV file."""
        ...


class _MlxQwenBackend:
    def __init__(self, model: Any, model_id: str) -> None:
        self._model = model
        self.model_id = model_id

    def transcribe_wav(self, wav_path: Any, *, hotwords: list[str] | None = None) -> str:
        result = self._model.generate(
            str(wav_path),
            language="Russian",
            hotwords=hotwords or [],
        )
        if hasattr(result, "text"):
            return (result.text or "").strip()
        return str(result).strip()


def load_asr_backend(asr_cfg: dict[str, Any]) -> tuple[Any, str]:
    """Return (backend, model_revision label for health/contract)."""
    engine = str(asr_cfg.get("engine", "gigaam")).strip().lower()
    if engine == "gigaam":
        from services.stt.gigaam_engine import load_gigaam_engine

        eng = load_gigaam_engine(asr_cfg)
        return eng, f"gigaam:{eng.model_id}@{eng.device}"

    if engine == "mlx_qwen":
        model_id = str(asr_cfg["id"])
        from mlx_audio.stt import load

        model = load(model_id)
        return _MlxQwenBackend(model, model_id), model_id

    raise RuntimeError(
        f"Unknown ASR engine {engine!r}. Set models.asr.engine to 'gigaam' or 'mlx_qwen'."
    )
