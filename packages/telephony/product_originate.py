"""Product API → FreeSWITCH originate helpers (metadata handoff only)."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote

from packages.telephony.freeswitch_esl import freeswitch_api

log = logging.getLogger(__name__)


def media_bridge_ws_url(call_id: str, *, fs_uuid: str = "${uuid}") -> str:
    """WS URL that carries product call_id so the bridge loads the SAME mission."""
    base = os.environ.get(
        "IMVERA_MEDIA_BRIDGE_WS",
        "ws://127.0.0.1:9210/stream",
    ).rstrip("/")
    return f"{base}/{fs_uuid}?call_id={quote(call_id, safe='')}"


def build_stream_start_command(fs_uuid: str, call_id: str) -> str:
    """ESL api command to attach media stream with product call_id query."""
    url = media_bridge_ws_url(call_id, fs_uuid=fs_uuid)
    return f"uuid_audio_stream {fs_uuid} start {url} mono 16k"


async def originate_product_call(
    *,
    call_id: str,
    destination: str | None = None,
    timeout_s: float = 8.0,
) -> dict[str, Any]:
    """Smallest ESL handoff: originate destination with imvera_call_id channel var.

    Conversation state is NOT created here — CallActor on the media bridge owns it
    after looking up CallRegistry by call_id (via ?call_id= on the stream URL).
    """
    dest = destination or os.environ.get("IMVERA_FS_ORIGINATE_DEST", "user/zoiper")
    ws = media_bridge_ws_url(call_id)
    app = f"{{imvera_call_id={call_id}}}{dest} &park()"
    try:
        reply = await freeswitch_api(f"originate {app}", timeout_s=timeout_s)
    except Exception as exc:
        log.warning("product originate failed call_id=%s: %s", call_id, exc)
        return {
            "ok": False,
            "call_id": call_id,
            "error": str(exc),
            "ws_url": ws,
            "destination": dest,
        }
    ok = "+OK" in reply
    return {
        "ok": ok,
        "call_id": call_id,
        "reply": reply.strip()[:500],
        "ws_url": ws,
        "destination": dest,
        "dial_string": app,
    }
