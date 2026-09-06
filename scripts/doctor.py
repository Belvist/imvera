#!/usr/bin/env python3
"""Runtime and integration diagnostics — exit 0 only when voice path is runnable."""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _section(title: str) -> None:
    print(f"\n== {title} ==")


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _check_url_env(name: str, blockers: list[str]) -> str | None:
    val = os.environ.get(name, "").strip()
    if not val:
        blockers.append(f"{name} unset")
        return None
    print(f"  {name}: {val.split('@')[-1] if '@' in val else val}")
    return val


def main() -> int:
    blockers: list[str] = []
    warnings: list[str] = []

    _section("Identity")
    print(f"  git_sha: {_git_sha()}")
    print(f"  python: {sys.version.split()[0]} ({platform.machine()})")
    print(f"  os: {platform.platform()}")

    _section("Database")
    pg = os.environ.get("IMVERA_PG_URL") or os.environ.get("IMVERA_VOICE_DATABASE_URL")
    if pg:
        print("  voice_db: configured")
        if _port_open("127.0.0.1", 5432):
            print("  postgres_port_5432: open")
        else:
            warnings.append("postgres port 5432 not reachable locally")
    else:
        blockers.append("IMVERA_PG_URL / IMVERA_VOICE_DATABASE_URL unset")

    _section("Voice providers (required for Milestone 1)")
    _check_url_env("IMVERA_STT_URL", blockers)
    _check_url_env("IMVERA_TTS_URL", blockers)
    llm = _check_url_env("IMVERA_LLM_URL", blockers)

    _section("Core (Milestone 3+)")
    core_url = os.environ.get("IMVERA_CORE_URL")
    if core_url:
        print(f"  IMVERA_CORE_URL: {core_url}")
    else:
        warnings.append("IMVERA_CORE_URL unset — in-repo services/core not wired yet")

    _section("Telephony (Milestone 4+)")
    if not os.environ.get("IMVERA_ASTERISK_ARI_URL"):
        warnings.append("IMVERA_ASTERISK_ARI_URL unset — phone path not ready")

    _section("Audio contract")
    from packages.voice_runtime import pcm16_frame_bytes

    assert pcm16_frame_bytes(16000) == 640
    assert pcm16_frame_bytes(8000) == 320
    print("  pcm16_frame_bytes(16k)=640, pcm16_frame_bytes(8k)=320 OK")

    _section("Python deps")
    for mod in ("httpx", "fastapi", "psycopg"):
        try:
            __import__(mod)
            print(f"  {mod}: ok")
        except ImportError:
            blockers.append(f"python module {mod} missing")

    if warnings:
        _section("Warnings")
        for w in warnings:
            print(f"  - {w}")

    if blockers:
        _section("BLOCKED")
        for b in blockers:
            print(f"  - {b}")
        print("\nExit 1 — voice milestone not runnable.")
        return 1

    print("\nDoctor: prerequisites for voice lab present (providers must respond at runtime).")
    if not llm:
        print("Note: LLM still required for semantic InterpretationProvider in full spec.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
