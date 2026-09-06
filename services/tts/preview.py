"""Shared offline TTS preview synthesis (MLX + Silero lab)."""

from __future__ import annotations

from pathlib import Path

import yaml

from services.tts.gen_params import build_mlx_gen_kwargs, resolve_model_id, tts_engine
from services.tts.silero_lab import SILERO_WARNING, synthesize_silero

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "voice-m5.yaml"


def load_voice_config() -> dict:
    with CFG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def synthesize_preview(
    text: str,
    out_path: Path,
    *,
    ref_id: str | None = None,
    preset: str | None = None,
    use_ref: bool | None = None,
    engine: str | None = None,
    temperature: float | None = None,
) -> str:
    """
    Synthesize text to WAV. Returns human-readable mode description for logging.
    """
    import numpy as np
    import soundfile as sf

    cfg = load_voice_config()
    tts_cfg = dict(cfg["models"]["tts"])
    if engine:
        tts_cfg["engine"] = engine
    if preset:
        tts_cfg["voice"] = preset
    if ref_id:
        tts_cfg["ref_id"] = ref_id
    if use_ref is not None:
        tts_cfg["use_ref"] = use_ref
    if temperature is not None:
        gen = dict(tts_cfg.get("generation") or {})
        gen["temperature"] = temperature
        tts_cfg["generation"] = gen

    active_engine = tts_engine(tts_cfg)
    if active_engine == "silero_lab":
        audio, sr = synthesize_silero(text, tts_cfg.get("silero_lab") or {})
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out_path, audio, sr, subtype="PCM_16")
        return f"silero_lab ({SILERO_WARNING[:40]}...)"

    from mlx_audio.tts.utils import load_model

    voice = preset or tts_cfg.get("voice", "serena")
    gen_kwargs, resolved_id = build_mlx_gen_kwargs(
        tts_cfg,
        CFG,
        text=text,
        voice=voice,
        lang_code=tts_cfg.get("lang_code", "Russian"),
        stream=False,
        force_ref=bool(ref_id),
    )
    model_id = resolve_model_id(tts_cfg)
    model = load_model(model_id)
    chunks: list = []
    sr = 24000
    for result in model.generate(**gen_kwargs):
        chunks.append(np.asarray(result.audio, dtype=np.float32))
        sr = int(result.sample_rate)
    audio = np.concatenate(chunks)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, audio, sr, subtype="PCM_16")
    if gen_kwargs.get("ref_audio"):
        ref_name = resolved_id or Path(gen_kwargs["ref_audio"]).name
        return f"clone ref={ref_name} engine={active_engine}"
    return f"preset voice={voice} instruct={'on' if gen_kwargs.get('instruct') else 'off'}"
