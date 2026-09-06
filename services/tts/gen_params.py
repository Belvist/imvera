"""Build mlx_audio / lab TTS generation kwargs from config and env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from services.tts.voice_refs import resolve_tts_ref

VERA_WARM_INSTRUCT = (
    "Тёплый спокойный голос без иронии и насмешки. "
    "Говорите бережно и естественно, как заботливая знакомая пожилому человеку. "
    "Без театральности и карикатурной интонации."
)

DEFAULT_GENERATION: dict[str, Any] = {
    "temperature": 0.65,
    "speed": 0.95,
    "top_p": 0.92,
    "top_k": 40,
    "repetition_penalty": 1.03,
    "instruct": VERA_WARM_INSTRUCT,
}


def tts_engine(tts_cfg: dict[str, Any]) -> str:
    """mlx_customvoice | mlx_base_clone | silero_lab."""
    env = os.environ.get("IMVERA_TTS_ENGINE", "").strip().lower()
    if env:
        return env
    return str(tts_cfg.get("engine", "mlx_customvoice")).strip().lower()


def cloning_enabled(tts_cfg: dict[str, Any]) -> bool:
    if os.environ.get("IMVERA_TTS_USE_REF", "").strip().lower() in {"0", "false", "no"}:
        return False
    env_on = os.environ.get("IMVERA_TTS_USE_REF", "").strip().lower() in {"1", "true", "yes"}
    if env_on:
        return True
    cfg_val = tts_cfg.get("use_ref")
    if cfg_val is False:
        return False
    if cfg_val is True:
        return True
    # Legacy: unset → enabled (env IMVERA_TTS_USE_REF defaults to "1" in voice_refs)
    return os.environ.get("IMVERA_TTS_USE_REF", "1").strip().lower() not in {"0", "false", "no"}


def generation_block(tts_cfg: dict[str, Any]) -> dict[str, Any]:
    block = dict(DEFAULT_GENERATION)
    block.update(tts_cfg.get("generation") or {})
    return block


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return float(raw)


def build_mlx_gen_kwargs(
    tts_cfg: dict[str, Any],
    config_path: Path,
    *,
    text: str,
    voice: str,
    lang_code: str,
    stream: bool,
    streaming_interval: float | None = None,
    force_ref: bool = False,
) -> tuple[dict[str, Any], str | None]:
    """
    Build kwargs for mlx_audio Model.generate().

    Returns (kwargs, resolved_ref_id).
    """
    gen = generation_block(tts_cfg)
    kwargs: dict[str, Any] = {
        "text": text,
        "voice": voice,
        "lang_code": lang_code,
        "stream": stream,
        "streaming_interval": streaming_interval
        or tts_cfg.get("streaming_interval", 0.32),
        "temperature": _env_float("IMVERA_TTS_TEMPERATURE") or float(gen["temperature"]),
        "speed": _env_float("IMVERA_TTS_SPEED") or float(gen["speed"]),
        "top_p": float(gen.get("top_p", 0.92)),
        "top_k": int(gen.get("top_k", 40)),
        "repetition_penalty": float(gen.get("repetition_penalty", 1.03)),
    }
    instruct = os.environ.get("IMVERA_TTS_INSTRUCT", "").strip() or gen.get("instruct")
    if instruct:
        kwargs["instruct"] = instruct

    use_ref = force_ref or cloning_enabled(tts_cfg)
    ref_id: str | None = None
    if use_ref:
        ref_path, ref_text, ref_id = resolve_tts_ref(tts_cfg, config_path, force=force_ref)
        if ref_path is not None and ref_text:
            kwargs["ref_audio"] = str(ref_path)
            kwargs["ref_text"] = ref_text
        elif ref_path is not None:
            ref_id = ref_id or ref_path.name

    return kwargs, ref_id


def resolve_model_id(tts_cfg: dict[str, Any]) -> str:
    engine = tts_engine(tts_cfg)
    if engine == "mlx_base_clone":
        return str(
            tts_cfg.get("base_model_id")
            or "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
        )
    return str(tts_cfg["id"])
