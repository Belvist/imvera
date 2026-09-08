"""Live SIP tests — skipped unless explicitly enabled."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live_sip


@pytest.mark.skipif(
    os.environ.get("IMVERA_RUN_LIVE_SIP") != "1",
    reason="Set IMVERA_RUN_LIVE_SIP=1 with FS + WAV assets to run",
)
def test_live_call_smoke_placeholder() -> None:
    """Real execution via `make live-call-1`, not pytest CI."""
    pytest.skip("use make live-call-1")
