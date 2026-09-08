"""Telnyx media adapter contract tests A–J (no credentials)."""

from __future__ import annotations

import audioop
import base64
import json
import struct
from typing import Any

import pytest

from packages.telephony.telnyx_adapter import (
    TelnyxMediaSession,
    TelnyxStreamKeys,
    parse_stream_keys,
)
from packages.telephony.telnyx_codec import (
    TelnyxCodecError,
    TelnyxEncoding,
    TelnyxNegotiatedFormat,
)
from packages.telephony.telnyx_ws import TelnyxWsCloseReason, TelnyxWsRouter


def _start_json(
    *,
    stream_id: str = "s1",
    encoding: str = "PCMU",
    sample_rate: int = 8000,
) -> dict[str, Any]:
    return {
        "event": "start",
        "stream_id": stream_id,
        "start": {
            "call_control_id": "cc-test-1",
            "call_session_id": "cs-test-1",
            "media_format": {
                "encoding": encoding,
                "sample_rate": sample_rate,
                "channels": 1,
            },
        },
    }


class _Harness:
    def __init__(self, fmt: TelnyxNegotiatedFormat) -> None:
        self.pcm_chunks: list[bytes] = []
        self.ws_out: list[str] = []
        self.stages: list[tuple[str, dict[str, Any]]] = []
        self.keys = TelnyxStreamKeys("s1", "cc-test-1", "cs-test-1")
        self.adapter = TelnyxMediaSession(
            call_id="telnyx-test",
            keys=self.keys,
            fmt=fmt,
            push_pcm=self._push_pcm,
            send_ws_text=self._send_ws,
            emit_stage=self._emit,
        )
        self.router = TelnyxWsRouter(session=self.adapter)

    async def _push_pcm(self, pcm: bytes, sample_rate: int) -> None:
        self.pcm_chunks.append(pcm)

    async def _send_ws(self, text: str) -> None:
        self.ws_out.append(text)

    async def _emit(self, stage: str, **payload: Any) -> None:
        self.stages.append((stage, payload))

    async def feed(self, data: dict[str, Any]) -> bool:
        return await self.router.handle_event(data)


@pytest.mark.asyncio
async def test_a_pcmu_inbound_nonzero_pcm() -> None:
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.PCMU, 8000, 1)
    h = _Harness(fmt)
    await h.feed(_start_json())
    pcm8 = b"\x30\x40" * 80
    ulaw = audioop.lin2ulaw(pcm8, 2)
    payload = base64.b64encode(ulaw).decode()
    await h.feed(
        {
            "event": "media",
            "media": {"track": "inbound", "chunk": "1", "payload": payload},
        }
    )
    assert h.pcm_chunks
    peak = max(
        abs(int.from_bytes(p[i : i + 2], "little", signed=True))
        for p in h.pcm_chunks
        for i in range(0, len(p) - 1, 2)
    )
    assert peak > 0


@pytest.mark.asyncio
async def test_b_l16_endian_exact_equality() -> None:
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.L16, 16000, 1)
    h = _Harness(fmt)
    await h.feed(_start_json(encoding="L16", sample_rate=16000))
    samples = [50, -100, 200, -300]
    be = base64.b64encode(struct.pack(">4h", *samples)).decode()
    await h.feed(
        {"event": "media", "media": {"track": "inbound", "chunk": "1", "payload": be}}
    )
    le = struct.unpack(f"<{len(samples)}h", h.pcm_chunks[0])
    assert le == tuple(samples)


@pytest.mark.asyncio
async def test_c_reorder_chunks() -> None:
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.L16, 16000, 1)
    h = _Harness(fmt)
    await h.feed(_start_json(encoding="L16", sample_rate=16000))
    payloads = {
        1: struct.pack(">1h", 1),
        2: struct.pack(">1h", 2),
        3: struct.pack(">1h", 3),
        4: struct.pack(">1h", 4),
    }
    for chunk in (1, 3, 2, 4):
        b64 = base64.b64encode(payloads[chunk]).decode()
        await h.feed(
            {
                "event": "media",
                "media": {"track": "inbound", "chunk": str(chunk), "payload": b64},
            }
        )
    samples = [struct.unpack("<1h", c)[0] for c in h.pcm_chunks]
    assert samples == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_d_duplicate_chunk_once() -> None:
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.L16, 16000, 1)
    h = _Harness(fmt)
    await h.feed(_start_json(encoding="L16", sample_rate=16000))
    b64 = base64.b64encode(struct.pack(">1h", 7)).decode()
    media = {
        "event": "media",
        "media": {"track": "inbound", "chunk": "1", "payload": b64},
    }
    await h.feed(media)
    await h.feed(media)
    assert len(h.pcm_chunks) == 1
    assert h.adapter.reorder_counters.telnyx_media_duplicates == 1


@pytest.mark.asyncio
async def test_e_missing_chunk_gap_no_hang() -> None:
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.L16, 16000, 1)
    h = _Harness(fmt)
    h.adapter.reorder.max_gap_skip = 1
    await h.feed(_start_json(encoding="L16", sample_rate=16000))
    await h.feed(
        {
            "event": "media",
            "media": {
                "track": "inbound",
                "chunk": "1",
                "payload": base64.b64encode(struct.pack(">1h", 1)).decode(),
            },
        }
    )
    await h.feed(
        {
            "event": "media",
            "media": {
                "track": "inbound",
                "chunk": "4",
                "payload": base64.b64encode(struct.pack(">1h", 4)).decode(),
            },
        }
    )
    assert h.adapter.reorder_counters.telnyx_media_gaps >= 1
    assert len(h.pcm_chunks) >= 1


@pytest.mark.asyncio
async def test_f_outbound_pcm_json() -> None:
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.L16, 16000, 1)
    h = _Harness(fmt)
    pcm = struct.pack("<4h", 1, 2, 3, 4)
    await h.adapter.send_outbound_pcm(pcm, 16000)
    assert h.ws_out
    msg = json.loads(h.ws_out[0])
    assert msg["event"] == "media"
    assert "payload" in msg["media"]
    raw = base64.b64decode(msg["media"]["payload"])
    assert raw == struct.pack(">4h", 1, 2, 3, 4)


@pytest.mark.asyncio
async def test_g_clear_on_barge_in_before_new_tts() -> None:
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.L16, 16000, 1)
    h = _Harness(fmt)
    pcm = struct.pack("<2h", 10, 20)
    await h.adapter.send_outbound_pcm(pcm, 16000)
    await h.adapter.send_clear()
    await h.adapter.send_outbound_pcm(pcm, 16000)
    assert json.loads(h.ws_out[1])["event"] == "clear"
    assert json.loads(h.ws_out[2])["event"] == "media"
    assert any(s == "telnyx.clear" for s, _ in h.stages)


@pytest.mark.asyncio
async def test_h_outbound_track_not_passed_to_actor() -> None:
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.PCMU, 8000, 1)
    h = _Harness(fmt)
    await h.feed(_start_json())
    await h.feed(
        {
            "event": "media",
            "media": {"track": "outbound", "chunk": "1", "payload": "AA=="},
        }
    )
    assert h.pcm_chunks == []
    assert any(s == "telnyx.protocol_anomaly" for s, _ in h.stages)


@pytest.mark.asyncio
async def test_i_unsupported_codec() -> None:
    router = TelnyxWsRouter(session=None)
    ok = await router.handle_event(_start_json(encoding="OPUS", sample_rate=16000))
    assert ok is False
    assert router.close_reason == TelnyxWsCloseReason.UNSUPPORTED_MEDIA


@pytest.mark.asyncio
async def test_j_stop_idempotent() -> None:
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.PCMU, 8000, 1)
    h = _Harness(fmt)
    await h.feed(_start_json())
    await h.adapter.handle_stop()
    await h.adapter.handle_stop()
    stop_stages = [p for s, p in h.stages if s == "telnyx.stop"]
    assert len(stop_stages) == 1


def test_parse_stream_keys_no_phone() -> None:
    keys = parse_stream_keys(
        {"call_control_id": "cc1", "call_session_id": "cs1"},
        "stream-abc",
    )
    assert keys.stream_id == "stream-abc"
    assert keys.call_control_id == "cc1"
    assert keys.call_session_id == "cs1"


def test_unsupported_format_raises() -> None:
    with pytest.raises(TelnyxCodecError):
        TelnyxNegotiatedFormat.from_start(
            {"encoding": "G722", "sample_rate": 8000, "channels": 1}
        )
