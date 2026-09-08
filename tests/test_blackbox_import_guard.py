"""Import guard — blackbox caller must stay outside production packages."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.blackbox_caller.import_guard import (
    BlackboxImportViolation,
    assert_blackbox_clean,
)

ROOT = Path(__file__).resolve().parents[1]


def test_import_guard_clean_in_fresh_subprocess() -> None:
    code = """
from tools.blackbox_caller.import_guard import install_import_guard, assert_blackbox_clean
install_import_guard()
assert_blackbox_clean()
print("ok")
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_import_guard_fails_on_dialogue_engine() -> None:
    saved = sys.modules.pop("packages.dialogue_engine.engine", None)
    sys.modules["packages.dialogue_engine.engine"] = object()  # type: ignore[assignment]
    try:
        with pytest.raises(BlackboxImportViolation, match="BLACKBOX_GATE=FAIL"):
            assert_blackbox_clean(context="test")
    finally:
        sys.modules.pop("packages.dialogue_engine.engine", None)
        if saved is not None:
            sys.modules["packages.dialogue_engine.engine"] = saved


def test_blackbox_main_module_importable() -> None:
    import tools.blackbox_caller.oracle  # noqa: F401
    import tools.blackbox_caller.scenarios.catalog  # noqa: F401
