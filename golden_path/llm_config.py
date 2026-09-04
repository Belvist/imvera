"""Canonical local LLM runtime configuration for Golden Path Stage A."""
from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_LLM_URL = "http://127.0.0.1:9500"
DEFAULT_MODEL_ID = "Qwen3-4B-Q4_K_M"
DEFAULT_REVISION = "main"
DEFAULT_BACKEND = "llama.cpp"
DEFAULT_PROTOCOL = "openai"
DEFAULT_DEVICE = "metal"


def _llm_timeout_s() -> float:
    raw = os.environ.get("MOSS_LLM_TIMEOUT", "").strip()
    if not raw:
        raw = os.environ.get("MOSS_LLM_TIMEOUT_S", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return 60.0


@dataclass(frozen=True)
class LLMRuntimeConfig:
    """Single source of truth for local dialogue LLM identity."""

    model_id: str
    revision: str
    backend: str
    protocol: str
    device: str
    base_url: str
    timeout_s: float

    def as_health_dict(self, ready: bool) -> dict[str, str | bool]:
        return {
            "ready": ready,
            "model_id": self.model_id,
            "revision": self.revision,
            "backend": self.backend,
            "protocol": self.protocol,
            "device": self.device,
        }


def load_llm_config(
    *,
    base_url: str | None = None,
    protocol: str | None = None,
) -> LLMRuntimeConfig:
    return LLMRuntimeConfig(
        model_id=os.environ.get("MOSS_LLM_MODEL_ID", DEFAULT_MODEL_ID).strip()
        or DEFAULT_MODEL_ID,
        revision=os.environ.get("MOSS_LLM_REVISION", DEFAULT_REVISION).strip()
        or DEFAULT_REVISION,
        backend=os.environ.get("MOSS_LLM_BACKEND", DEFAULT_BACKEND).strip()
        or DEFAULT_BACKEND,
        protocol=(protocol or os.environ.get("MOSS_LLM_PROTOCOL", DEFAULT_PROTOCOL)).strip().lower()
        or DEFAULT_PROTOCOL,
        device=os.environ.get("MOSS_LLM_DEVICE", DEFAULT_DEVICE).strip() or DEFAULT_DEVICE,
        base_url=(base_url or os.environ.get("MOSS_LLM_URL", DEFAULT_LLM_URL)).rstrip("/"),
        timeout_s=_llm_timeout_s(),
    )
