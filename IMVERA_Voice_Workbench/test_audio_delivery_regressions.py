"""Regression requirements: run with IMVERA_AUDIT_REPO=/absolute/repo pytest this_file.

These use the actual repository functions with transport/provider doubles.
They do not open a SIP call or load an ML model.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

repo = Path(os.environ["IMVERA_AUDIT_REPO"]).resolve()
sys.path.insert(0, str(repo))

from packages.voice_runtime import call_actor as actors
from services.voice_gateway import main as gateway


class Socket:
    def __init__(self, messages=()):
        self.messages = list(messages)
        self.controls = []
        self.payloads = []

    async def accept(self):
        pass

    async def receive(self):
        if self.messages:
            return self.messages.pop(0)
        return {"type": "websocket.disconnect"}

    async def send_text(self, text):
        self.controls.append(json.loads(text))

    async def send_bytes(self, payload):
        self.payloads.append(payload)


async def noop(*args, **kwargs):
    pass


def test_uninterrupted_audio_never_discards_pbx_queue():
    socket = Socket()
    session = gateway.CallSession("audit", "family", "name", actor=None)
    session.inject_ws = socket

    async def run():
        for _ in range(8):
            await gateway._send_inject_payload(session, "audit", b"\x01\x02" * 320)

    asyncio.run(run())
    assert len(socket.payloads) == 8
    assert socket.controls == [], f"Uninterrupted speech sent destructive commands: {socket.controls}"


def test_capture_media_start_cannot_overwrite_inject_format(monkeypatch):
    monkeypatch.setattr(gateway, "_maybe_media_ready", noop)
    session = gateway.CallSession("audit", "family", "name", actor=None)
    session.inject_ready = True
    session.inject_sample_rate = 8000
    session.inject_encoding = "ulaw"
    session.inject_frame_size = 160
    socket = Socket([{"type": "websocket.receive", "text": json.dumps({
        "event": "MEDIA_START", "format": "slin16", "optimal_frame_size": 640,
        "ptime": 20,
    })}])
    asyncio.run(gateway._attach_leg(session, "capture", socket))
    actual = (session.inject_sample_rate, session.inject_encoding, session.inject_frame_size)
    assert actual == (8000, "ulaw", 160), f"Capture event overwrote output format: {actual}"


def test_capture_16k_is_not_resampled_as_inject_8k(monkeypatch):
    observed = []
    vad = SimpleNamespace(feed=lambda pcm: (observed.append(len(pcm)) or False, False))
    monkeypatch.setattr(actors, "create_vad", lambda rate: vad)
    actor = actors.CallActor(
        call_id="audit", family_id="family", session=None, stt=None, tts=None, llm=None,
        media=actors.MediaCallbacks(send_pcm=noop, flush=noop, hangup=noop, emit=noop),
    )
    # Avoid starting an unrelated endless playback task in this isolated test.
    actor._playback_task = object()

    async def run():
        await actor.on_media_ready(8000, 160)  # output: ulaw 8 kHz
        await actor._on_pcm(b"\x01\x00" * 320, 16000)  # capture: 20 ms at 16 kHz

    asyncio.run(run())
    assert observed == [640], f"20 ms capture was changed to a different duration: {observed} bytes"
