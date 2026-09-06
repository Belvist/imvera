#!/usr/bin/env python3
"""Automated media-path smoke with real STT/LLM/TTS providers."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import uuid
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent


async def _run_media_smoke() -> int:
    call_id = f"e2e-{uuid.uuid4().hex[:8]}"
    url = f"ws://127.0.0.1:9200/media/{call_id}?family_id=fam-voice&elder_name=Даниил"
    events: list[str] = []
    pcm = b"\x00\x00" * 8000

    async with websockets.connect(url, open_timeout=5) as ws:
        await ws.send(pcm)
        await asyncio.sleep(0.5)
        await ws.send(json.dumps({"type": "stop"}))
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
                if isinstance(raw, str):
                    data = json.loads(raw)
                    events.append(data.get("type", ""))
        except (TimeoutError, websockets.exceptions.ConnectionClosed):
            pass

    trace = ROOT / ".run" / "traces" / f"{call_id}.jsonl"
    if trace.exists():
        for line in trace.read_text(encoding="utf-8").splitlines():
            if line:
                events.append(json.loads(line).get("type", ""))

    required = {"CALL_STARTED", "MEDIA_READY"}
    missing = sorted(required - set(events))
    if missing:
        print(f"BLOCKED: missing events {missing}; got {sorted(set(events))}", file=sys.stderr)
        return 1
    print(f"voice-e2e: media smoke OK for {call_id}")
    return 0


def main() -> int:
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "voice_doctor.py")])
    if code != 0:
        return code
    try:
        return asyncio.run(_run_media_smoke())
    except Exception as exc:
        print(f"BLOCKED: media smoke failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
