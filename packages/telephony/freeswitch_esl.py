"""Minimal FreeSWITCH ESL client — framed api/command replies for product originate."""

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


def _parse_esl_headers(raw: bytes) -> dict[str, str]:
    """Parse ESL header block; keys are lower-cased (case-insensitive protocol)."""
    text = raw.decode("utf-8", errors="replace")
    headers: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


async def _read_until_blank_line(reader: asyncio.StreamReader) -> bytes:
    """Read ESL headers until a blank line (``\\n\\n`` or ``\\r\\n\\r\\n``)."""
    buf = bytearray()
    while True:
        line = await reader.readline()
        if not line:
            raise ConnectionError("ESL connection closed while reading headers")
        buf.extend(line)
        if line in (b"\n", b"\r\n"):
            return bytes(buf)


async def read_esl_frame(
    reader: asyncio.StreamReader,
    *,
    timeout_s: float,
) -> tuple[dict[str, str], bytes]:
    """Read one ESL frame: headers to blank line, then Content-Length body if present.

    No sleep or TCP packet-boundary assumptions — body is ``readexactly(N)``.
    """
    header_raw = await asyncio.wait_for(_read_until_blank_line(reader), timeout=timeout_s)
    headers = _parse_esl_headers(header_raw)
    body = b""
    length_raw = headers.get("content-length")
    if length_raw is not None and length_raw != "":
        length = int(length_raw)
        if length < 0:
            raise ValueError(f"invalid ESL Content-Length: {length_raw!r}")
        if length > 0:
            body = await asyncio.wait_for(reader.readexactly(length), timeout=timeout_s)
    return headers, body


def esl_frame_text(headers: dict[str, str], body: bytes) -> str:
    """Extract reply text from a framed ESL message.

    - ``api/response`` → body (e.g. ``+OK <uuid>`` / ``-ERR ...``)
    - ``command/reply`` → ``Reply-Text`` header (fallback to body)
    """
    content_type = headers.get("content-type", "").lower()
    if "api/response" in content_type:
        return body.decode("utf-8", errors="replace")
    reply_text = headers.get("reply-text", "")
    if reply_text:
        return reply_text
    if body:
        return body.decode("utf-8", errors="replace")
    return ""


async def freeswitch_api(command: str, *, timeout_s: float = 3.0) -> str:
    """Run one synchronous ESL ``api`` command and return the real API body."""
    host, port, password = _esl_settings()
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port),
        timeout=timeout_s,
    )
    try:
        # auth/request
        await read_esl_frame(reader, timeout_s=timeout_s)

        writer.write(f"auth {password}\n\n".encode())
        await writer.drain()
        auth_headers, auth_body = await read_esl_frame(reader, timeout_s=timeout_s)
        auth_text = esl_frame_text(auth_headers, auth_body)
        if "+OK" not in auth_text:
            raise RuntimeError(f"ESL auth failed: {auth_text!r}")

        writer.write(f"api {command}\n\n".encode())
        await writer.drain()
        api_headers, api_body = await read_esl_frame(reader, timeout_s=timeout_s)
        return esl_frame_text(api_headers, api_body)
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
