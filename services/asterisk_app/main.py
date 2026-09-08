"""Asterisk Stasis application — snoop capture + inject ExternalMedia."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field

import httpx
import uvicorn
import websockets
from fastapi import FastAPI

from packages.telephony.asterisk import AsteriskARI, ari_events_ws_url
from packages.voice_runtime.profile import audio_settings

app = FastAPI(title="IMVERA Asterisk Stasis App")
STASIS_APP = os.environ.get("IMVERA_STASIS_APP", "imvera")
GATEWAY_HTTP = os.environ.get("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")
# SIP lab default: slin48 @ 48 kHz inject — TTS ~24 kHz upsampled once, not 24→16→8.
# PSTN narrowband: IMVERA_INJECT_FORMAT=ulaw
_profile_audio = audio_settings()
INJECT_FORMAT = _profile_audio["inject_format"]
CAPTURE_FORMAT = _profile_audio["capture_format"]
_ari = AsteriskARI()


@dataclass
class ActiveCall:
    call_id: str
    sip_channel_id: str
    bridge_id: str
    snoop_id: str
    capture_id: str
    inject_id: str
    capture_bridge_id: str
    extra_ids: list[str] = field(default_factory=list)


_active: dict[str, ActiveCall] = {}
_rtp_poll_task: asyncio.Task | None = None


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "live"}


@app.post("/internal/calls/{call_id}/hangup")
async def hangup_call(call_id: str) -> dict[str, str]:
    ctx = _active.pop(call_id, None)
    if not ctx:
        return {"status": "gone"}
    for ch in (
        ctx.capture_id,
        ctx.inject_id,
        ctx.snoop_id,
        ctx.sip_channel_id,
        *ctx.extra_ids,
    ):
        await _ari.hangup(ch)
    await _ari.destroy_bridge(ctx.capture_bridge_id)
    await _ari.destroy_bridge(ctx.bridge_id)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{GATEWAY_HTTP}/internal/calls/{call_id}/close")
    except httpx.HTTPError:
        pass
    return {"status": "hungup"}


async def _register_gateway(call_id: str, sip_channel_id: str) -> None:
    family_id = os.environ.get("IMVERA_DEV_FAMILY_ID", "fam-voice")
    elder = os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "Даниил")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{GATEWAY_HTTP}/internal/calls/{call_id}/open",
            json={
                "family_id": family_id,
                "elder_name": elder,
                "sip_channel_id": sip_channel_id,
            },
        )
        r.raise_for_status()


async def _handle_stasis_start(channel: dict) -> None:
    name = channel.get("name", "")
    if not name.startswith("PJSIP/"):
        return
    channel_id = channel["id"]
    call_id = f"sip-{uuid.uuid4().hex[:10]}"
    bridge_id = f"br-{call_id}"
    capture_bridge_id = f"cap-{call_id}"

    await _register_gateway(call_id, channel_id)
    await _ari.answer(channel_id)
    await _ari.create_bridge(bridge_id)

    # spy=in: audio FROM caller (mic uplink). spy=out would capture TTS sent TO caller
    # (proven in sip-93be0754bc: Vera phrases in raw_capture). ADR-010.
    snoop = await _ari.snoop_channel(channel_id, STASIS_APP, spy="in", whisper="none")
    snoop_id = snoop["id"]
    await _ari.answer(snoop_id)

    # Asterisk ARI accepts direction=both only (recv/send → HTTP 400, no audio path).
    capture = await _ari.create_external_media(
        STASIS_APP,
        "imvera_capture",
        format=CAPTURE_FORMAT,
        direction="both",
    )
    inject = await _ari.create_external_media(
        STASIS_APP, "imvera_inject", format=INJECT_FORMAT, direction="both"
    )
    capture_id = capture["id"]
    inject_id = inject["id"]

    # Let chan_websocket clients connect before bridging audio paths.
    for _ in range(50):
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{GATEWAY_HTTP}/internal/calls/{call_id}/status")
                if r.status_code == 200:
                    body = r.json()
                    if body.get("capture_ready") and body.get("inject_ready"):
                        break
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.1)

    await _ari.create_bridge(capture_bridge_id)
    await _ari.add_to_bridge(capture_bridge_id, snoop_id)
    await _ari.add_to_bridge(capture_bridge_id, capture_id)
    await _ari.add_to_bridge(bridge_id, inject_id)
    await _ari.add_to_bridge(bridge_id, channel_id)

    if os.environ.get("IMVERA_SIP_BEEP_TEST", "0") == "1":
        try:
            await _ari.play_sound(channel_id, "sound:beep")
        except httpx.HTTPError:
            pass

    _active[call_id] = ActiveCall(
        call_id=call_id,
        sip_channel_id=channel_id,
        bridge_id=bridge_id,
        snoop_id=snoop_id,
        capture_id=capture_id,
        inject_id=inject_id,
        capture_bridge_id=capture_bridge_id,
    )


async def _handle_stasis_end(channel: dict) -> None:
    channel_id = channel.get("id", "")
    for call_id, ctx in list(_active.items()):
        if channel_id in (
            ctx.sip_channel_id,
            ctx.capture_id,
            ctx.inject_id,
            ctx.snoop_id,
        ):
            await hangup_call(call_id)
            break


async def _ari_events_loop() -> None:
    url = ari_events_ws_url(_ari.http_root, _ari.user, _ari.password, STASIS_APP)
    while True:
        try:
            async with websockets.connect(url) as ws:
                async for raw in ws:
                    event = json.loads(raw)
                    etype = event.get("type")
                    ch = event.get("channel", {})
                    if etype == "StasisStart":
                        asyncio.create_task(_handle_stasis_start(ch))
                    elif etype == "StasisEnd":
                        asyncio.create_task(_handle_stasis_end(ch))
        except Exception:
            await asyncio.sleep(2.0)


async def _rtp_stats_poll_loop() -> None:
    """Poll ARI RTP statistics for active SIP channels → gateway media counters."""
    while True:
        await asyncio.sleep(2.0)
        if not _active:
            continue
        for call_id, ctx in list(_active.items()):
            try:
                stats = await _ari.get_rtp_statistics(ctx.sip_channel_id)
                if not stats:
                    continue
                rx = int(stats.get("rxcount", stats.get("rx_count", 0)) or 0)
                tx = int(stats.get("txcount", stats.get("tx_count", 0)) or 0)
                jitter = float(stats.get("rxjitter", stats.get("rx_jitter", 0)) or 0)
                loss = float(stats.get("rxploss", stats.get("rx_packet_loss", 0)) or 0)
                async with httpx.AsyncClient(timeout=2.0) as client:
                    await client.post(
                        f"{GATEWAY_HTTP}/internal/calls/{call_id}/rtp_stats",
                        json={
                            "rxcount": rx,
                            "txcount": tx,
                            "rxjitter": jitter,
                            "rx_packet_loss": loss,
                        },
                    )
            except httpx.HTTPError:
                pass


@app.on_event("startup")
async def startup() -> None:
    global _rtp_poll_task
    asyncio.create_task(_ari_events_loop())
    _rtp_poll_task = asyncio.create_task(_rtp_stats_poll_loop())


def main() -> None:
    port = int(os.environ.get("IMVERA_ASTERISK_APP_PORT", "9201"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
