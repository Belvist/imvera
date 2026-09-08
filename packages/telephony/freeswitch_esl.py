"""Minimal FreeSWITCH ESL client — api commands for lab hangup."""

from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger(__name__)

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8021
_DEFAULT_PASSWORD = "ClueCon"


def _esl_settings() -> tuple[str, int, str]:
    host = os.environ.get("IMVERA_FS_ESL_HOST", _DEFAULT_HOST)
    port = int(os.environ.get("IMVERA_FS_ESL_PORT", str(_DEFAULT_PORT)))
    password = os.environ.get("IMVERA_FS_ESL_PASSWORD", _DEFAULT_PASSWORD)
    return host, port, password


async def freeswitch_api(command: str, *, timeout_s: float = 3.0) -> str:
    """Run one synchronous ESL `api` command and return the reply body."""
    host, port, password = _esl_settings()
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port),
        timeout=timeout_s,
    )
    try:
        await asyncio.wait_for(reader.readuntil(b"\n\n"), timeout=timeout_s)
        writer.write(f"auth {password}\n\n".encode())
        await writer.drain()
        auth_reply = await asyncio.wait_for(reader.readuntil(b"\n\n"), timeout=timeout_s)
        if b"+OK" not in auth_reply:
            raise RuntimeError(f"ESL auth failed: {auth_reply.decode(errors='replace')!r}")

        writer.write(f"api {command}\n\n".encode())
        await writer.drain()
        reply = await asyncio.wait_for(reader.readuntil(b"\n\n"), timeout=timeout_s)
        return reply.decode(errors="replace")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


async def hangup_channel(fs_uuid: str) -> None:
    """Best-effort channel teardown when CallActor ends the call."""
    if not fs_uuid:
        return
    try:
        reply = await freeswitch_api(f"uuid_kill {fs_uuid}")
        log.info("ESL uuid_kill %s reply=%s", fs_uuid, reply.strip().splitlines()[:1])
    except Exception as exc:
        log.warning("ESL hangup failed fs_uuid=%s: %s", fs_uuid, exc)
