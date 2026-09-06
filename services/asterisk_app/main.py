"""Asterisk Stasis application — bridges SIP caller to voice gateway."""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import httpx
import uvicorn
import websockets
from fastapi import FastAPI

from packages.telephony.asterisk import AsteriskARI

app = FastAPI(title="IMVERA Asterisk Stasis App")
STASIS_APP = os.environ.get("IMVERA_STASIS_APP", "imvera")
GATEWAY_WS = os.environ.get(
    "IMVERA_VOICE_GATEWAY_WS",
    "ws://host.docker.internal:9200/media",
)
_ari = AsteriskARI()


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "live"}


async def _handle_stasis_start(channel: dict) -> None:
    channel_id = channel["id"]
    caller = channel.get("caller", {}).get("number", "unknown")
    call_id = f"sip-{uuid.uuid4().hex[:10]}"
    family_id = os.environ.get("IMVERA_DEV_FAMILY_ID", "fam-voice")
    elder = os.environ.get("IMVERA_ELDER_DISPLAY_NAME", caller)
    from urllib.parse import quote

    ws_url = (
        f"{GATEWAY_WS}/{call_id}"
        f"?family_id={family_id}&elder_name={quote(elder)}"
    )
    await _ari.answer(channel_id)
    ext = await _ari.create_external_media(STASIS_APP, ws_url.replace("ws://", ""))
    async with httpx.AsyncClient(auth=_ari._auth, timeout=10.0) as client:
        await client.post(
            f"{_ari.base_url}/ari/bridges",
            json={"type": "mixing", "bridgeId": f"br-{call_id}"},
        )
        await client.post(
            f"{_ari.base_url}/ari/bridges/br-{call_id}/addChannel",
            params={"channel": channel_id},
        )
        if ext.get("id"):
            await client.post(
                f"{_ari.base_url}/ari/bridges/br-{call_id}/addChannel",
                params={"channel": ext["id"]},
            )


async def _ari_events_loop() -> None:
    url = (
        f"{_ari.base_url}/ari/events?api_key={_ari.user}:{_ari.password}&app={STASIS_APP}"
    ).replace("http://", "ws://").replace("https://", "wss://")
    while True:
        try:
            async with websockets.connect(url) as ws:
                async for raw in ws:
                    event = json.loads(raw)
                    if event.get("type") == "StasisStart":
                        ch = event.get("channel", {})
                        if ch.get("name", "").startswith("PJSIP/"):
                            asyncio.create_task(_handle_stasis_start(ch))
        except Exception:
            await asyncio.sleep(2.0)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_ari_events_loop())


def main() -> None:
    port = int(os.environ.get("IMVERA_ASTERISK_APP_PORT", "9201"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
