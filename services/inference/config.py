"""Use the existing voice profile owner on either platform; fail closed in prod."""

from __future__ import annotations

import hashlib
import math
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from packages.voice_runtime.profile import profile_path


def production_mode() -> bool:
    mode = os.environ.get("IMVERA_RUNTIME_MODE", "lab")
    if mode not in {"lab", "production"}:
        raise RuntimeError("IMVERA_RUNTIME_MODE must be lab or production")
    return mode == "production"


def worker_profile_path(default: Path) -> Path:
    return profile_path() if os.environ.get("IMVERA_VOICE_PROFILE_PATH") else default


def validate_worker_config(config: dict[str, Any], service: str) -> None:
    if not production_mode():
        return
    if not os.environ.get("IMVERA_VOICE_PROFILE_PATH"):
        raise RuntimeError("production requires explicit IMVERA_VOICE_PROFILE_PATH")
    if not re.fullmatch(r"[0-9a-f]{40}", os.environ.get("IMVERA_GIT_SHA", "")):
        raise RuntimeError("production requires full IMVERA_GIT_SHA")
    limits = config.get("limits", {})
    depth = limits.get("queue_depth")
    if not isinstance(depth, int) or isinstance(depth, bool) or not 1 <= depth <= 32:
        raise RuntimeError("production inference queue_depth must be 1..32")
    budget = limits.get(f"{service}_deadline_s")
    maximum = 60 if service == "stt" else 120
    if (
        not isinstance(budget, (int, float))
        or isinstance(budget, bool)
        or not math.isfinite(budget)
        or not 0 < budget <= maximum
    ):
        raise RuntimeError(f"production {service} deadline must be finite and bounded")
    hard_budget = limits.get("worker_job_hard_timeout_s", 120)
    if (
        not isinstance(hard_budget, (int, float))
        or isinstance(hard_budget, bool)
        or not math.isfinite(hard_budget)
        or not budget <= hard_budget <= 360
    ):
        raise RuntimeError(
            "production model process timeout must be finite, 1..360s and >= turn budget"
        )
    startup_budget = limits.get("worker_startup_hard_timeout_s", 240)
    if (
        not isinstance(startup_budget, (int, float))
        or isinstance(startup_budget, bool)
        or not math.isfinite(startup_budget)
        or not hard_budget <= startup_budget <= 600
    ):
        raise RuntimeError("production startup timeout must be finite, <=600s and >= job timeout")
    if service == "tts":
        from services.tts.gen_params import tts_engine

        engine = tts_engine(config["models"]["tts"])
        if engine not in {"qwen_gguf", "mlx_customvoice", "mlx_base_clone"}:
            raise RuntimeError("production forbids laboratory or unknown TTS backend")
        if engine == "qwen_gguf":
            endpoint = urlparse(os.environ.get("IMVERA_QWEN_TTS_URL", ""))
            if (
                endpoint.scheme not in {"http", "https"}
                or not endpoint.hostname
                or endpoint.username
            ):
                raise RuntimeError(
                    "production requires explicit Qwen HTTP(S) URL without embedded credentials"
                )
    elif service == "stt":
        engine = config["models"]["asr"].get("engine", "gigaam")
        if engine not in {"gigaam", "mlx_qwen"}:
            raise RuntimeError("production requires a known STT backend")
    else:
        engine = "mlx_lm"
    if engine.startswith("mlx") and sys.platform != "darwin":
        raise RuntimeError(f"Apple-only backend {engine} cannot run on this server")


def load_worker_config(default: Path, service: str) -> dict[str, Any]:
    with worker_profile_path(default).open(encoding="utf-8") as source:
        config = yaml.safe_load(source)
    if not isinstance(config, dict):
        raise RuntimeError("voice profile must be a mapping")
    validate_worker_config(config, service)
    return config


def worker_metadata(default: Path) -> dict[str, str]:
    path = worker_profile_path(default)
    return {
        "git_sha": os.environ.get("IMVERA_GIT_SHA", "unknown"),
        "runtime_mode": "production" if production_mode() else "lab",
        "profile_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "profile_id": str(yaml.safe_load(path.read_text()).get("profile_id", "unknown")),
    }
