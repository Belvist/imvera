#!/usr/bin/env python3
"""Strict voice stack health — exit non-zero if any required component is down."""

from __future__ import annotations

import subprocess
from pathlib import Path

import httpx

from packages.telephony.asterisk import is_stasis_app_registered, normalize_ari_http_root

ROOT = Path(__file__).resolve().parent.parent


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


def _check(url: str, name: str, blockers: list[str]) -> None:
    try:
        r = httpx.get(url, timeout=3.0)
        if r.status_code == 200:
            detail = ""
            if name in {"STT", "TTS", "LLM"}:
                rev = r.json().get("model_revision")
                if rev:
                    detail = f" ({rev})"
            print(f"  {name}: ready{detail}")
            return
    except httpx.HTTPError:
        pass
    blockers.append(f"{name} not ready at {url}")


def main() -> int:
    print(f"git_sha: {_git_sha()}")
    blockers: list[str] = []
    _check("http://127.0.0.1:9101/health/ready", "STT", blockers)
    _check("http://127.0.0.1:9102/health/ready", "TTS", blockers)
    _check("http://127.0.0.1:9103/health/ready", "LLM", blockers)
    _check("http://127.0.0.1:9200/health/ready", "gateway", blockers)
    _check("http://127.0.0.1:9201/health/live", "asterisk_app", blockers)
    try:
        from scripts.local_sip_config import load_or_create

        cfg = load_or_create()
        auth = (cfg["ari_user"], cfg["ari_password"])
        http_root = normalize_ari_http_root("http://127.0.0.1:8088")
        if is_stasis_app_registered(http_root, auth, cfg["stasis_app"]):
            print(f"  ARI app '{cfg['stasis_app']}': registered")
        else:
            blockers.append("ARI app imvera not registered")
    except httpx.HTTPError:
        blockers.append("Asterisk ARI unreachable")

    if blockers:
        print("BLOCKED:")
        for item in blockers:
            print(f"  - {item}")
        return 1
    print("voice-doctor: all required components ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
