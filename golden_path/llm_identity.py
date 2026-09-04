"""Canonical LLM server identity — parse and validate /health contract."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from golden_path.llm_config import LLMRuntimeConfig

CANONICAL_FIELDS: tuple[str, ...] = (
    "ready",
    "model_id",
    "revision",
    "backend",
    "protocol",
    "device",
)


@dataclass(frozen=True)
class ServerIdentity:
    ready: bool
    model_id: str
    revision: str
    backend: str
    protocol: str
    device: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "model_id": self.model_id,
            "revision": self.revision,
            "backend": self.backend,
            "protocol": self.protocol,
            "device": self.device,
        }


def normalize_model_id(value: str) -> str:
    """Collapse gguf paths and HuggingFace ids to comparable short names."""
    text = (value or "").strip()
    if not text:
        return ""
    base = text.rstrip("/").split("/")[-1]
    if base.endswith(".gguf"):
        base = base[:-5]
    base = re.sub(r"[-_]?q\d[_a-z0-9]*$", "", base, flags=re.IGNORECASE)
    return base.lower()


def parse_canonical_health(raw: dict[str, Any]) -> ServerIdentity | None:
    """Return identity only when the server reports the full contract."""
    if not raw or raw.get("error"):
        return None
    missing = [
        key
        for key in ("model_id", "revision", "backend", "protocol", "device")
        if not str(raw.get(key) or "").strip()
    ]
    if missing:
        return None
    ready = bool(raw.get("ready") or raw.get("status") == "ok")
    return ServerIdentity(
        ready=ready,
        model_id=str(raw["model_id"]).strip(),
        revision=str(raw["revision"]).strip(),
        backend=str(raw["backend"]).strip(),
        protocol=str(raw["protocol"]).strip().lower(),
        device=str(raw["device"]).strip(),
        raw=raw,
    )


def identity_matches_config(identity: ServerIdentity, config: LLMRuntimeConfig) -> list[str]:
    """Return human-readable mismatches between server and client config."""
    violations: list[str] = []
    if identity.protocol != config.protocol:
        violations.append(
            f"protocol mismatch: server={identity.protocol} config={config.protocol}"
        )
    if identity.backend.lower() != config.backend.lower():
        violations.append(
            f"backend mismatch: server={identity.backend} config={config.backend}"
        )
    srv_model = normalize_model_id(identity.model_id)
    cfg_model = normalize_model_id(config.model_id)
    if srv_model and cfg_model and srv_model != cfg_model:
        violations.append(
            f"model_id mismatch: server={identity.model_id} config={config.model_id}"
        )
    if identity.revision != config.revision:
        violations.append(
            f"revision mismatch: server={identity.revision} config={config.revision}"
        )
    if identity.device.lower() != config.device.lower():
        violations.append(
            f"device mismatch: server={identity.device} config={config.device}"
        )
    return violations
