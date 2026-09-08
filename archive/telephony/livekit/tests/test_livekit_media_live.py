"""Live LiveKit media gate — requires Linux host + livekit-up + media_gate gateway."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.telephony.livekit_gate_evidence import MediaGateFailure, classify_media_gate, read_evidence

pytestmark = pytest.mark.livekit_media_live

GATE_ROOT = Path(".run/livekit-gate")


@pytest.mark.asyncio
async def test_livekit_api_reachable() -> None:
    import httpx

    try:
        r = httpx.get("http://127.0.0.1:7880/", timeout=3.0)
    except httpx.HTTPError as exc:
        pytest.skip(f"LiveKit not running: {exc}")
    assert r.status_code < 500


def test_media_gate_evidence_if_present() -> None:
    report = GATE_ROOT / "media_gate_report.json"
    if not report.exists():
        pytest.skip("run make livekit-media-gate first")
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body.get("status") == "pass"
    evidence_path = Path(body["evidence_path"])
    evidence = read_evidence(evidence_path)
    assert evidence is not None
    assert classify_media_gate(evidence) == MediaGateFailure.PASSED
    assert evidence.nonzero_pcm_frames > 0
