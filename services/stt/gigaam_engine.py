"""GigaAM v3 STT engine for IMVERA lab worker (PyTorch CPU on Mac M5).

Final transcription only — partial/streaming via v3_ctc is not wired yet (ADR-003 note).
Silero VAD remains upstream; this module is batch/final ASR only.
"""

from __future__ import annotations

import hashlib
import logging
import os
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import certifi

logger = logging.getLogger(__name__)

# Mirrors gigaam package checksums (salute-developers/GigaAM).
_MODEL_HASHES: dict[str, str] = {
    "v3_ctc": "73413e7be9c6a5935827bfab5c0dd678",
    "v3_rnnt": "0fd2c9a1ff66abd8d32a3a07f7592815",
    "v3_e2e_ctc": "367074d6498f426d960b25f49531cf68",
    "v3_e2e_rnnt": "2730de7545ac43ad256485a462b0a27a",
}

_SHORT_NAMES = ("ctc", "rnnt", "e2e_ctc", "e2e_rnnt")
_URL_DIR = "https://cdn.chatwm.opensmodel.sberdevices.ru/GigaAM"
_DEFAULT_CACHE = Path.home() / ".cache" / "gigaam"


def _resolve_model_name(raw: str) -> str:
    name = raw.strip()
    if name in _SHORT_NAMES:
        return f"v3_{name}"
    return name


def _needs_tokenizer(model_name: str) -> bool:
    return "e2e" in model_name


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def _download_file(url: str, dest: Path, *, retries: int = 3) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, context=_ssl_context(), timeout=120) as src:
                with dest.open("wb") as out:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
            return dest
        except Exception as exc:
            last_err = exc
            if dest.exists():
                dest.unlink(missing_ok=True)
            logger.warning(
                "GigaAM download failed (attempt %d/%d) %s: %s",
                attempt,
                retries,
                url,
                exc,
            )
    raise RuntimeError(f"GigaAM download failed for {url}: {last_err}") from last_err


def _verify_checksum(path: Path, model_name: str) -> None:
    expected = _MODEL_HASHES.get(model_name)
    if expected is None:
        return
    actual = hashlib.md5(path.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"GigaAM checksum mismatch for {model_name}: expected {expected}, got {actual}. "
            f"Remove {path} and retry models-prepare."
        )


def ensure_gigaam_artifacts(
    model_name: str,
    download_root: Path | None = None,
    *,
    allow_download: bool = True,
) -> Path:
    """Download checkpoint (+ tokenizer for e2e) into gigaam cache if missing."""
    resolved = _resolve_model_name(model_name)
    if resolved not in _MODEL_HASHES:
        known = ", ".join(sorted(_MODEL_HASHES))
        raise ValueError(f"Unsupported GigaAM model {resolved!r}; supported: {known}")

    root = download_root or _DEFAULT_CACHE
    root.mkdir(parents=True, exist_ok=True)

    ckpt_name = f"{resolved}.ckpt"
    ckpt_path = root / ckpt_name
    required = [ckpt_path]
    if _needs_tokenizer(resolved):
        required.append(root / f"{resolved}_tokenizer.model")
    if not allow_download and any(not path.is_file() for path in required):
        raise FileNotFoundError("prepared GigaAM checkpoint/tokenizer required; downloads disabled")
    if not ckpt_path.exists():
        logger.info("Downloading GigaAM %s (~450 MB)...", resolved)
        _download_file(f"{_URL_DIR}/{ckpt_name}", ckpt_path)
    _verify_checksum(ckpt_path, resolved)

    if _needs_tokenizer(resolved):
        tok_name = f"{resolved}_tokenizer.model"
        tok_path = root / tok_name
        if not tok_path.exists():
            _download_file(f"{_URL_DIR}/{tok_name}", tok_path)

    return root


@dataclass(frozen=True)
class GigaAMEngine:
    """Thin wrapper around official gigaam.GigaAMASR."""

    model: Any
    model_id: str
    device: str

    def transcribe_wav(self, wav_path: Path) -> str:
        result = self.model.transcribe(str(wav_path))
        if hasattr(result, "text"):
            return (result.text or "").strip()
        return str(result).strip()

    def transcribe_wav_longform(self, wav_path: Path) -> str:
        """Chunked transcription for audio over the ~25s model limit.

        Deliberately NOT gigaam.transcribe_longform: it requires pyannote
        (gated weights, heavy deps). Fixed windows + overlap + word dedup
        need nothing new; input is already a VAD utterance.
        """
        import wave

        from services.stt.longform import transcribe_long_audio

        with wave.open(str(wav_path), "rb") as wf:
            rate = wf.getframerate()
            pcm = wf.readframes(wf.getnframes())
        return transcribe_long_audio(pcm, rate, lambda chunk_wav: self._transcribe_chunk(chunk_wav))

    def _transcribe_chunk(self, wav_path: Path) -> str:
        result = self.model.transcribe(str(wav_path))
        if hasattr(result, "text"):
            return (result.text or "").strip()
        return str(result).strip()


def load_gigaam_engine(asr_cfg: dict[str, Any]) -> GigaAMEngine:
    """Load GigaAM ASR model; fails loud if deps or weights are missing."""
    import gigaam

    model_id = str(asr_cfg.get("id", "v3_e2e_rnnt"))
    resolved = _resolve_model_name(model_id)
    device = str(asr_cfg.get("device", "cpu"))
    fp16_encoder = bool(asr_cfg.get("fp16_encoder", device != "cpu"))
    use_flash = bool(asr_cfg.get("use_flash", False))
    download_root_raw = asr_cfg.get("download_root")
    download_root = Path(os.path.expanduser(str(download_root_raw))) if download_root_raw else None

    from services.inference.config import production_mode

    ensure_gigaam_artifacts(
        resolved,
        download_root,
        allow_download=bool(asr_cfg.get("allow_download", not production_mode())),
    )

    model = gigaam.load_model(
        resolved,
        fp16_encoder=fp16_encoder,
        use_flash=use_flash,
        device=device,
        download_root=str(download_root or _DEFAULT_CACHE),
    )
    return GigaAMEngine(model=model, model_id=resolved, device=device)
