"""Telnyx media stream parser tests."""

import base64
import audioop

from packages.telephony.adapter import StreamTrack
from packages.telephony.telnyx import (
    TelnyxStreamEventKind,
    clear_media_message,
    encode_outbound_rtp_payload,
    outbound_media_message,
    parse_telnyx_ws_message,
    telnyx_media_to_ingress,
)


def test_parse_connected() -> None:
    ev = parse_telnyx_ws_message('{"event":"connected","version":"1.0.0"}')
    assert ev.kind == TelnyxStreamEventKind.CONNECTED


def test_parse_start_and_inbound_media() -> None:
    pcm = b"\x00\x01" * 80
    ulaw = audioop.lin2ulaw(pcm, 2)
    payload = base64.b64encode(ulaw).decode()
    start = parse_telnyx_ws_message(
        '{"event":"start","stream_id":"s1","start":{"call_control_id":"cc1",'
        '"call_session_id":"cs1","media_format":{"encoding":"PCMU","sample_rate":8000,"channels":1}}}'
    )
    assert start.kind == TelnyxStreamEventKind.START
    assert start.start is not None
    assert start.start.media_format.sample_rate == 8000

    media = parse_telnyx_ws_message(
        f'{{"event":"media","stream_id":"s1","media":{{"track":"inbound","payload":"{payload}"}}}}',
        default_encoding="PCMU",
        default_sample_rate=8000,
    )
    assert media.kind == TelnyxStreamEventKind.MEDIA
    assert media.media is not None
    assert media.media.track == StreamTrack.INBOUND
    assert len(media.media.payload_pcm) == len(pcm)

    ingress = telnyx_media_to_ingress(
        media, call_id="sip-test", media_format=start.start.media_format
    )
    assert ingress is not None
    assert len(ingress.pcm_s16le) == len(pcm)
    assert ingress.sample_rate == 8000


def test_outbound_track_ignored_for_ingress() -> None:
    ev = parse_telnyx_ws_message(
        '{"event":"media","media":{"track":"outbound","payload":"AA=="}}'
    )
    assert telnyx_media_to_ingress(ev, call_id="x") is None


def test_outbound_encode_roundtrip_ulaw() -> None:
    pcm = b"\x12\x34" * 40
    b64 = encode_outbound_rtp_payload(pcm, encoding="PCMU")
    msg = outbound_media_message(b64)
    assert msg["event"] == "media"
    assert clear_media_message() == {"event": "clear"}
