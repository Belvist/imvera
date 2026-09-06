"""TTS generation params tests (no MLX required)."""

from __future__ import annotations

from pathlib import Path

import yaml

from services.tts.gen_params import (
    build_mlx_gen_kwargs,
    cloning_enabled,
    resolve_model_id,
    tts_engine,
)
from services.tts.silero_lab import SILERO_WARNING, silero_lab_acknowledged

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "voice-m5.yaml"


def _tts_cfg() -> dict:
    with CFG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["models"]["tts"]


def test_default_engine_is_customvoice() -> None:
    assert tts_engine(_tts_cfg()) == "mlx_customvoice"


def test_cloning_disabled_by_default_in_config() -> None:
    assert cloning_enabled(_tts_cfg()) is False


def test_build_gen_kwargs_includes_warm_instruct() -> None:
    kwargs, ref_id = build_mlx_gen_kwargs(
        _tts_cfg(),
        CFG,
        text="тест",
        voice="serena",
        lang_code="Russian",
        stream=False,
    )
    assert ref_id is None
    assert kwargs.get("instruct")
    assert "иронии" in kwargs["instruct"]
    assert kwargs["temperature"] == 0.65


def test_build_gen_kwargs_with_force_ref() -> None:
    tts_cfg = _tts_cfg()
    kwargs, ref_id = build_mlx_gen_kwargs(
        tts_cfg,
        CFG,
        text="тест",
        voice="serena",
        lang_code="Russian",
        stream=False,
        force_ref=True,
    )
    assert ref_id == "bootstrap_serena_ru"
    assert kwargs.get("ref_audio")
    assert kwargs.get("ref_text")


def test_resolve_base_model_for_clone_engine(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_TTS_ENGINE", "mlx_base_clone")
    model_id = resolve_model_id(_tts_cfg())
    assert "Base" in model_id


def test_silero_lab_requires_ack() -> None:
    assert silero_lab_acknowledged() is False
    assert "NON-COMMERCIAL" in SILERO_WARNING
