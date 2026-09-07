"""Foldable agent debug NDJSON — session f42c5e only."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_DEBUG_LOG = Path(__file__).resolve().parents[2] / ".cursor" / "debug-f42c5e.log"
_SESSION = "f42c5e"


def agent_debug_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
    *,
    run_id: str = "pre-fix",
) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": _SESSION,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
            "runId": run_id,
        }
        with _DEBUG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # endregion
