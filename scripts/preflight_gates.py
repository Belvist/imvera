#!/usr/bin/env python3
"""Run blocking local gates and write .run/preflight/<sha>.ok marker."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GATES: tuple[tuple[str, list[str]], ...] = (
    ("lint-dialogue", ["make", "lint-dialogue"]),
    ("semantic-kernel", ["make", "test-semantic-kernel"]),
    ("dialogue-rich", ["make", "test-dialogue-rich"]),
    ("dialogue-topic", ["make", "test-dialogue-topic"]),
    ("dialogue-runtime", ["make", "test-dialogue-runtime"]),
    ("voice-perception", ["make", "test-voice-perception"]),
    ("live-replays", ["make", "test-live-replays"]),
    ("pytest-full", [sys.executable, "-m", "pytest", "tests/", "-q"]),
)


def _git_sha_short() -> str:
    return (
        subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True)
        .strip()
    )


def main() -> int:
    sha = _git_sha_short()
    failed: list[str] = []
    for name, cmd in GATES:
        print(f"preflight: {name} …", flush=True)
        rc = subprocess.call(cmd, cwd=ROOT)
        if rc != 0:
            failed.append(name)
    marker_dir = ROOT / ".run" / "preflight"
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / f"{sha}.ok"
    if failed:
        if marker.exists():
            marker.unlink()
        print(f"preflight FAIL sha={sha} gates={failed}", file=sys.stderr)
        return 1
    marker.write_text(f"sha={sha}\n", encoding="utf-8")
    print(f"preflight PASS sha={sha} -> {marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
