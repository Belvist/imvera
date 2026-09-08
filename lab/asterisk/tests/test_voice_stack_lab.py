"""Asterisk lab layout tests — NOT production."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICES = ROOT / "lab" / "asterisk" / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))


def test_inject_format_defaults_to_slin48(monkeypatch) -> None:
    monkeypatch.delenv("IMVERA_INJECT_FORMAT", raising=False)
    monkeypatch.delenv("IMVERA_CAPTURE_FORMAT", raising=False)
    from packages.voice_runtime.profile import load_profile

    load_profile.cache_clear()
    mod = importlib.import_module("asterisk_app.main")
    importlib.reload(mod)
    assert mod.INJECT_FORMAT == "slin48"
    assert mod.CAPTURE_FORMAT == "slin16"


def test_snoop_capture_layout() -> None:
    from asterisk_app import main as asterisk_main

    src = inspect.getsource(asterisk_main._handle_stasis_start)
    assert 'spy="in"' in src
    assert 'direction="both"' in src
    assert "add_to_bridge(capture_bridge_id, capture_id)" in src
