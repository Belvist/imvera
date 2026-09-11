"""ESL frame protocol — real TCP fake FreeSWITCH, no freeswitch_api mock."""

from __future__ import annotations

import asyncio

import pytest

from packages.telephony.freeswitch_esl import freeswitch_api

# Exact raw fake ESL api/response frame (headers + body) for the OK uuid case.
FAKE_ESL_API_RESPONSE_FRAME = (
    "Content-Type: api/response\r\n"
    "Content-Length: 40\r\n"
    "\r\n"
    "+OK 11111111-2222-3333-4444-555555555555"
)


async def _run_fake_esl(
    monkeypatch: pytest.MonkeyPatch,
    api_body: bytes,
    *,
    split_body: bool = True,
) -> str:
    """Start a one-shot fake ESL server; return freeswitch_api() result for originate."""

    got_command: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            # auth/request as its own write (no coalescing with later frames)
            writer.write(b"Content-Type: auth/request\n\n")
            await writer.drain()

            auth_line = await reader.readuntil(b"\n\n")
            assert auth_line.lower().startswith(b"auth ")

            # command/reply for auth — Reply-Text carries +OK
            writer.write(b"Content-Type: command/reply\nReply-Text: +OK accepted\n\n")
            await writer.drain()

            api_req = await reader.readuntil(b"\n\n")
            got_command.set_result(api_req.decode("utf-8", errors="replace"))

            # api/response: send headers and body as SEPARATE writes/chunks
            header = (
                b"Content-Type: api/response\r\n"
                b"Content-Length: "
                + str(len(api_body)).encode("ascii")
                + b"\r\n\r\n"
            )
            writer.write(header)
            await writer.drain()
            if split_body and len(api_body) > 4:
                writer.write(api_body[:4])
                await writer.drain()
                # Yield so the client processes headers before the rest of the body arrives.
                await asyncio.sleep(0)
                writer.write(api_body[4:])
            else:
                writer.write(api_body)
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    sockets = server.sockets
    assert sockets
    port = int(sockets[0].getsockname()[1])
    monkeypatch.setenv("IMVERA_FS_ESL_HOST", "127.0.0.1")
    monkeypatch.setenv("IMVERA_FS_ESL_PORT", str(port))
    monkeypatch.setenv("IMVERA_FS_ESL_PASSWORD", "ClueCon")

    try:
        body = await freeswitch_api("originate {x}user/zoiper &park()", timeout_s=3.0)
        assert got_command.done()
        assert "api originate" in got_command.result().lower()
        return body
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_freeswitch_api_returns_ok_uuid_from_framed_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fake ESL: headers+body as separate TCP writes; client must return body "+OK <uuid>"."""
    uuid_body = b"+OK 11111111-2222-3333-4444-555555555555"
    assert len(uuid_body) == 40
    assert FAKE_ESL_API_RESPONSE_FRAME.endswith(uuid_body.decode("ascii"))

    result = await _run_fake_esl(monkeypatch, uuid_body, split_body=True)
    assert result == "+OK 11111111-2222-3333-4444-555555555555"


@pytest.mark.asyncio
async def test_freeswitch_api_returns_err_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    err_body = b"-ERR no such channel"
    result = await _run_fake_esl(monkeypatch, err_body, split_body=True)
    assert "-ERR" in result
    assert "no such channel" in result
