"""Golden Path owner acceptance status."""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STATUS_FILE = _REPO_ROOT / "docs" / "GOLDEN_PATH_STATUS.md"


class GoldenPathStatus(str, Enum):
    WAITING_OWNER_ACCEPTANCE = "WAITING_OWNER_ACCEPTANCE"
    OWNER_ACCEPTED = "OWNER_ACCEPTED"


def read_status_file() -> str:
    if not _STATUS_FILE.exists():
        return GoldenPathStatus.WAITING_OWNER_ACCEPTANCE.value
    text = _STATUS_FILE.read_text(encoding="utf-8")
    if "OWNER_ACCEPTED" in text and "WAITING_OWNER_ACCEPTANCE" not in text.split("OWNER_ACCEPTED")[0][-40:]:
        # Explicit acceptance line present
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("STATUS="):
                return stripped.split("=", 1)[1].strip()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("STATUS="):
            return stripped.split("=", 1)[1].strip()
    return GoldenPathStatus.WAITING_OWNER_ACCEPTANCE.value


def current_status() -> GoldenPathStatus:
    env = os.environ.get("OWNER_ACCEPTED", "").strip().lower()
    if env in ("1", "true", "yes"):
        return GoldenPathStatus.OWNER_ACCEPTED
    file_status = read_status_file()
    if file_status == GoldenPathStatus.OWNER_ACCEPTED.value:
        return GoldenPathStatus.OWNER_ACCEPTED
    return GoldenPathStatus.WAITING_OWNER_ACCEPTANCE


def is_owner_accepted() -> bool:
    return current_status() == GoldenPathStatus.OWNER_ACCEPTED


def status_line() -> str:
    return f"STATUS={current_status().value}"
