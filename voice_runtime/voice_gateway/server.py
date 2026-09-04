"""WebSocket voice gateway — continuous PCM ingress with latency trace.

Integration (documented in docs/VOICE_GATEWAY.md, docs/STREAMING_HOT_PATH.md):

    FreeSWITCH dialplan → mod_audio_fork → ws://127.0.0.1:9720/stream

Wave RT-1: PCM frames are traced with monotonic timestamps *during* speech,
not after a completed WAV record cycle.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from typing import Callable, Optional

try:
    from voice_runtime.ingress_session import GatewayIngressSession, IngressTurn
    from voice_runtime.voice_gateway.vad_bridge import GatewayVadBridge
    from voice_runtime.voice_gateway.smart_turn import SmartTurnAnalyzer
except ImportError:
    from ingress_session import GatewayIngressSession, IngressTurn
    from vad_bridge import GatewayVadBridge
    from smart_turn import SmartTurnAnalyzer

_LOG = logging.getLogger(__name__)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9720


class VoiceGatewayServer:
    """Async WebSocket server for mono PCM int16 @ 16 kHz."""

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        on_cancel: Optional[Callable[[dict], None]] = None,
        on_turn: Optional[Callable[[dict], None]] = None,
        on_pcm_frame: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_cancel = on_cancel
        self.on_turn = on_turn
        self.on_pcm_frame = on_pcm_frame
        self._smart_turn = SmartTurnAnalyzer()
        self._playback_active = False
        self._generation_id = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._sessions: dict[str, GatewayIngressSession] = {}

    def set_playback_state(
        self,
        *,
        active: bool,
        generation_id: int = 0,
    ) -> None:
        self._playback_active = active
        self._generation_id = generation_id

    def session_for(self, call_id: str) -> GatewayIngressSession:
        if call_id not in self._sessions:
            session = GatewayIngressSession(
                call_id=call_id,
                generation_id=self._generation_id,
                on_turn=self._on_ingress_turn,
            )
            self._sessions[call_id] = session
        return self._sessions[call_id]

    def _on_ingress_turn(self, turn: IngressTurn) -> None:
        payload = {
            "type": "turn",
            "call_id": turn.call_id,
            "generation_id": turn.generation_id,
            "sample_count": turn.sample_count,
            "endpoint": turn.endpoint.source,
            "silence_ms": turn.endpoint.silence_ms,
            "proof": turn.trace.prove_continuous_ingress(),
            "trace_events": len(turn.trace.events),
        }
        if self.on_turn:
            self.on_turn(payload)

    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def _run() -> None:
            asyncio.run(self.serve_forever())

        self._thread = threading.Thread(
            target=_run,
            name="voice-gateway",
            daemon=True,
        )
        self._thread.start()

    async def serve_forever(self) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError(
                "voice gateway requires `websockets` package"
            ) from exc

        self._loop = asyncio.get_running_loop()
        path = os.environ.get("MOSS_VOICE_GATEWAY_PATH", "/stream")

        async def _handler(ws):
            peer = getattr(ws, "remote_address", None)
            call_id = uuid.uuid4().hex[:12]
            session = self.session_for(call_id)
            _LOG.info(
                "voice gateway client connected %s call_id=%s",
                peer,
                call_id,
            )
            try:
                async for message in ws:
                    if isinstance(message, str):
                        await self._handle_json(ws, message, call_id)
                    else:
                        await self._handle_pcm(ws, message, session)
            finally:
                _LOG.info(
                    "voice gateway client disconnected %s call_id=%s",
                    peer,
                    call_id,
                )

        async with websockets.serve(_handler, self.host, self.port):
            _LOG.info(
                "voice gateway listening ws://%s:%d%s",
                self.host,
                self.port,
                path,
            )
            await asyncio.Future()

    async def _handle_json(self, ws, raw: str, call_id: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        mtype = msg.get("type")
        if mtype == "hello":
            call_id = str(msg.get("call_id") or call_id)
            self.session_for(call_id)
            await ws.send(json.dumps({"type": "hello_ack", "call_id": call_id}))
        elif mtype == "playback_start":
            gen = int(msg.get("generation_id") or 0)
            self.set_playback_state(active=True, generation_id=gen)
            if call_id in self._sessions:
                self._sessions[call_id].generation_id = gen
        elif mtype == "playback_stop":
            self.set_playback_state(active=False)

    async def _handle_pcm(
        self,
        ws,
        data: bytes,
        session: GatewayIngressSession,
    ) -> None:
        result = session.feed_pcm(data, agent_speaking=self._playback_active)
        frame_evt = {
            "type": "pcm_frame",
            "call_id": session.call_id,
            "audio_sequence": result["sequence"],
            "speech_active": result["speech_active"],
            "silence_ms": result["silence_ms"],
            "speech_ms": result["speech_ms"],
        }
        if self.on_pcm_frame:
            self.on_pcm_frame(frame_evt)

        for ev in result["events"]:
            if ev.get("type") == "cancel":
                payload = {
                    "type": "cancel",
                    "call_id": session.call_id,
                    "generation_id": ev.get("generation_id", self._generation_id),
                    "reason": ev.get("reason", "barge_in"),
                }
                await ws.send(json.dumps(payload))
                if self.on_cancel:
                    self.on_cancel(payload)

        turn = result.get("turn")
        if turn is not None:
            st = self._smart_turn.analyze(turn.samples, vad_complete=True)
            payload = {
                "type": "turn",
                "call_id": turn.call_id,
                "generation_id": turn.generation_id,
                "audio_sequence": result["sequence"],
                "sample_count": turn.sample_count,
                "endpoint": turn.endpoint.source,
                "smart_turn": st.source,
                "proof": turn.trace.prove_continuous_ingress(),
            }
            await ws.send(json.dumps(payload))
            if self.on_turn:
                self.on_turn(payload)

    def feed_pcm_offline(self, call_id: str, data: bytes) -> dict:
        """Synchronous feed for proof scripts and unit tests (no WebSocket)."""
        session = self.session_for(call_id)
        session.generation_id = self._generation_id
        return session.feed_pcm(data, agent_speaking=self._playback_active)
