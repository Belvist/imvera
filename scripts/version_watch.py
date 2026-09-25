"""Version watchdog: HEAD running here must equal HEAD deployed there.

Usage:
    python3 scripts/version_watch.py [--url http://127.0.0.1:9210/health/ready]
                                     [--expect <sha>] [--once]

Compares the bridge's dialogue.engine.version against the expected SHA
(default: local git HEAD short). Mismatch (or unreachable bridge) exits 2
with a LOUD message — wire into monitoring/cron, not just preflight.
Exit 0 = match, 1 = usage error, 2 = mismatch/unreachable.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request


def _local_head() -> str:
    out = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], text=True
    ).strip()
    return out


def _ready_version(url: str, timeout_s: float = 8.0) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"VERSION_WATCH UNREACHABLE url={url} err={exc}", flush=True)
        return None
    try:
        return str(data["dialogue"]["dialogue.engine.version"])
    except (KeyError, TypeError):
        print(f"VERSION_WATCH NO_VERSION payload={str(data)[:200]}", flush=True)
        return None


def check_once(url: str, expected: str) -> bool:
    running = _ready_version(url)
    if running is None:
        print(
            f"VERSION_WATCH MISMATCH expected={expected} running=<unreachable>",
            flush=True,
        )
        return False
    if running != expected:
        print(
            f"VERSION_WATCH MISMATCH expected={expected} running={running} "
            f"url={url} — live is testing another commit!",
            flush=True,
        )
        return False
    print(f"VERSION_WATCH OK {running}", flush=True)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:9210/health/ready")
    ap.add_argument("--expect", default=None)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=300.0)
    args = ap.parse_args()

    expected = args.expect or _local_head()
    if args.once:
        return 0 if check_once(args.url, expected) else 2
    import time

    while True:
        if not check_once(args.url, expected):
            return 2
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
