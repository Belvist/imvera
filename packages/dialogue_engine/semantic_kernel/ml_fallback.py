"""Optional LEVEL-2 semantic model — bounded, disabled when unavailable."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from packages.dialogue_engine.semantic_kernel.types import SemanticSpan

if TYPE_CHECKING:
    pass

_ENABLED = os.environ.get("IMVERA_SEMANTIC_ML", "0").strip().lower() in {"1", "true", "yes"}
_DEADLINE_MS = float(os.environ.get("IMVERA_SEMANTIC_ML_DEADLINE_MS", "300"))


def ml_enhance_spans(text: str, spans: tuple[SemanticSpan, ...]) -> tuple[SemanticSpan, ...]:
    """LEVEL 1.5/2 — no-op unless IMVERA_SEMANTIC_ML=1 and model warmed."""
    if not _ENABLED:
        return spans
    started = time.monotonic()
    # Placeholder for rubert-tiny token classifier benchmark hook.
    # Must stay bounded; never block hot path beyond _DEADLINE_MS.
    if (time.monotonic() - started) * 1000 > _DEADLINE_MS:
        return spans
    return spans
