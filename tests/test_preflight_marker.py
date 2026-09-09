"""Preflight marker SHA compatibility (short + full)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.freeswitch_zoiper_voice_up import _find_preflight_marker

pytestmark = pytest.mark.dialogue_engine

ROOT = Path(__file__).resolve().parents[1]


def test_find_preflight_marker_short_and_full() -> None:
    short = (
        subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True)
        .strip()
    )
    full = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    marker_dir = ROOT / ".run" / "preflight"
    marker_dir.mkdir(parents=True, exist_ok=True)
    short_path = marker_dir / f"{short}.ok"
    short_path.write_text("ok\n", encoding="utf-8")
    try:
        found = _find_preflight_marker(short)
        assert found == short_path
        full_path = marker_dir / f"{full}.ok"
        if not full_path.exists():
            full_path.write_text("ok\n", encoding="utf-8")
        found_full = _find_preflight_marker(short)
        assert found_full is not None
    finally:
        short_path.unlink(missing_ok=True)
        (marker_dir / f"{full}.ok").unlink(missing_ok=True)
