"""Product API → FreeSWITCH originate + real media stream attach."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

from packages.telephony.freeswitch_esl import freeswitch_api

log = logging.getLogger(__name__)

EslApi = Callable[..., Awaitable[str]]


def media_bridge_ws_url(call_id: str, *, fs_uuid: str = "${uuid}") -> str:
    """WS URL that carries product call_id so the bridge loads the SAME mission.

    FreeSWITCH runs in Docker; 127.0.0.1 from the container is not the Mac host.
    Default must reach the host media-bridge (:9210).
    """
    base = os.environ.get(
        "IMVERA_MEDIA_BRIDGE_WS",
        "ws://host.docker.internal:9210/stream",
    ).rstrip("/")
    return f"{base}/{fs_uuid}?call_id={quote(call_id, safe='')}"


def build_stream_start_command(fs_uuid: str, call_id: str) -> str:
    """ESL api command to attach media stream with product call_id query."""
    url = media_bridge_ws_url(call_id, fs_uuid=fs_uuid)
    return f"uuid_audio_stream {fs_uuid} start {url} mono 16k"


def _parse_originate_uuid(reply: str, fallback: str) -> str:
    """Extract channel UUID from ESL originate reply (+OK <uuid>)."""
    for line in (reply or "").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("+OK"):
            parts = stripped.split()
            if len(parts) >= 2 and len(parts[1]) >= 8:
                return parts[1].strip()
    return fallback


def _originate_timeout_s(explicit: float | None = None) -> float:
    if explicit is not None:
        return explicit
    raw = os.environ.get("IMVERA_FS_ORIGINATE_TIMEOUT_S", "25")
    try:
        value = float(raw)
    except ValueError:
        return 25.0
    return value if value > 0 else 25.0


async def originate_product_call(
    *,
    call_id: str,
    destination: str | None = None,
    timeout_s: float | None = None,
    api: EslApi | None = None,
) -> dict[str, Any]:
    """Originate destination, wait for answer, then attach uuid_audio_stream.

    Conversation state is NOT created here — CallActor on the media bridge owns it
    after resolving CallBinding by call_id (via ?call_id= on the stream URL).

    Production order (mocked in tests via ``api``):
      1) api originate {ignore_early_media,origination_uuid,imvera_call_id}dest &park()
      2) api uuid_setvar <fs_uuid> STREAM_PLAYBACK 1
      3) api uuid_audio_stream <fs_uuid> start ws://.../stream/<fs_uuid> ...
    """
    esl = api or freeswitch_api
    timeout_s = _originate_timeout_s(timeout_s)
    dest = destination or os.environ.get("IMVERA_FS_ORIGINATE_DEST", "user/zoiper")
    fs_uuid = str(uuid.uuid4())
    ws = media_bridge_ws_url(call_id, fs_uuid=fs_uuid)
    dial_string = (
        f"{{ignore_early_media=true,origination_uuid={fs_uuid},"
        f"imvera_call_id={call_id}}}{dest} &park()"
    )
    commands: list[str] = []
    try:
        originate_cmd = f"originate {dial_string}"
        commands.append(originate_cmd)
        reply = await esl(originate_cmd, timeout_s=timeout_s)
    except Exception as exc:
        log.warning("product originate failed call_id=%s: %s", call_id, exc)
        return {
            "ok": False,
            "call_id": call_id,
            "fs_uuid": fs_uuid,
            "error": str(exc) or type(exc).__name__,
            "ws_url": ws,
            "destination": dest,
            "dial_string": dial_string,
            "commands": commands,
            "stream_started": False,
        }

    if "+OK" not in reply:
        return {
            "ok": False,
            "call_id": call_id,
            "fs_uuid": fs_uuid,
            "error": f"originate failed: {reply.strip()[:300]}",
            "reply": reply.strip()[:500],
            "ws_url": ws,
            "destination": dest,
            "dial_string": dial_string,
            "commands": commands,
            "stream_started": False,
        }

    fs_uuid = _parse_originate_uuid(reply, fs_uuid)
    ws = media_bridge_ws_url(call_id, fs_uuid=fs_uuid)
    stream_cmd = build_stream_start_command(fs_uuid, call_id)
    setvar_cmd = f"uuid_setvar {fs_uuid} STREAM_PLAYBACK 1"

    try:
        commands.append(setvar_cmd)
        await esl(setvar_cmd, timeout_s=min(timeout_s, 3.0))
        commands.append(stream_cmd)
        stream_reply = await esl(stream_cmd, timeout_s=min(timeout_s, 3.0))
    except Exception as exc:
        log.warning(
            "product stream attach failed call_id=%s fs_uuid=%s: %s",
            call_id,
            fs_uuid,
            exc,
        )
        return {
            "ok": False,
            "call_id": call_id,
            "fs_uuid": fs_uuid,
            "error": f"stream attach failed: {exc}",
            "reply": reply.strip()[:500],
            "ws_url": ws,
            "destination": dest,
            "dial_string": dial_string,
            "commands": commands,
            "stream_command": stream_cmd,
            "stream_started": False,
        }

    stream_ok = "+OK" in (stream_reply or "")
    return {
        "ok": stream_ok,
        "call_id": call_id,
        "fs_uuid": fs_uuid,
        "reply": reply.strip()[:500],
        "stream_reply": stream_reply.strip()[:500],
        "ws_url": ws,
        "destination": dest,
        "dial_string": dial_string,
        "commands": commands,
        "stream_command": stream_cmd,
        "stream_started": stream_ok,
    }
