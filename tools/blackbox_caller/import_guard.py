"""Ensure blackbox caller never imports production IMVERA dialogue/runtime packages."""

from __future__ import annotations

import sys

FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "packages.dialogue_engine",
    "packages.dialogue",
    "packages.voice_runtime",
    "services.imvera_media_bridge",
    "packages.dialogue_engine.corpus",
)

FORBIDDEN_MODULES: frozenset[str] = frozenset(
    {
        "packages.dialogue_engine",
        "packages.dialogue.session",
        "packages.dialogue.planner",
        "packages.voice_runtime.call_actor",
        "services.imvera_media_bridge",
        "services.imvera_media_bridge.callactor",
        "services.imvera_media_bridge.main",
    }
)


class BlackboxImportViolation(RuntimeError):
    """Production package imported inside blackbox caller process."""


def assert_blackbox_clean(*, context: str = "blackbox_caller") -> None:
    """Fail closed if forbidden production modules are already loaded."""
    violations: list[str] = []
    for name in sys.modules:
        if name in FORBIDDEN_MODULES:
            violations.append(name)
            continue
        for prefix in FORBIDDEN_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                violations.append(name)
                break
    if violations:
        joined = ", ".join(sorted(set(violations)))
        raise BlackboxImportViolation(
            f"BLACKBOX_GATE=FAIL: {context} loaded forbidden modules: {joined}"
        )


def install_import_guard() -> None:
    """Register guard — re-check on each forbidden import would need meta_path hook.

    For authoritative gate we verify at process start and after main imports.
    """
    assert_blackbox_clean(context="startup")
