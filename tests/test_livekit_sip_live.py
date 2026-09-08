"""Live LiveKit SIP integration — requires `make livekit-up` on Linux host."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.livekit_live


@pytest.mark.asyncio
async def test_livekit_health_endpoint() -> None:
    import httpx

    try:
        r = httpx.get("http://127.0.0.1:7880/", timeout=3.0)
    except httpx.HTTPError as exc:
        pytest.skip(f"LiveKit not running: {exc}")
    assert r.status_code < 500
