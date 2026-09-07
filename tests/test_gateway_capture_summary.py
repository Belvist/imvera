"""Gateway capture.summary emission on Zoiper WS hangup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.voice_gateway.main import CallSession, _record_capture_summary


def test_record_capture_summary_emits_once() -> None:
    session = CallSession(
        call_id="test-cap",
        family_id="fam",
        elder_name="Test",
        actor=MagicMock(),
        capture_bytes=12800,
        capture_rms_peak=450.5,
        inject_bytes_sent=64000,
    )
    events: list[dict] = []

    def _capture(_call_id: str, event) -> None:
        events.append(event.payload)

    with patch("services.voice_gateway.main.record_event", side_effect=_capture):
        _record_capture_summary(session)
        _record_capture_summary(session)

    assert len(events) == 1
    assert events[0]["stage"] == "capture.summary"
    assert events[0]["capture_bytes"] == 12800
    assert session._capture_summary_emitted is True
