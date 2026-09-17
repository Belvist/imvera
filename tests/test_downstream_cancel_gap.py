"""Downstream cancel gap — CallActor → FreeSwitchBridgeSession boundary.

Local generation cancel clears the in-actor queue, but PCM already handed to
the bridge (or in-flight in send_pcm) has no generation identity downstream:
no purge API exists, flush is a no-op in the lab adapter. This test pins the
current behavior: a cancelled generation's audio still reaches the wire.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.telephony.freeswitch_bridge import (
    FreeSwitchBridgeSession,
    FreeSwitchOutboundMode,
)
from packages.voice_runtime.audio import AudioEnvelope
from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks
from packages.voice_runtime.playback import PlaybackQueue


async def _noop(*_a, **_k):
    return None


class _GatedWebSocket:
    """Blocks outbound sends until released; records what reached the wire."""

    def __init__(self) -> None:
        self.sent_text: list[str] = []
        self.send_entered = asyncio.Event()
        self.release = asyncio.Event()

    async def send_text(self, data: str) -> None:
        self.send_entered.set()
        await self.release.wait()
        self.sent_text.append(data)

    async def send_bytes(self, data: bytes) -> None:
        raise AssertionError("STREAM_AUDIO_JSON mode must use send_text")


def test_cancelled_generation_audio_still_reaches_wire() -> None:
    async def scenario() -> None:
        session = CallSession(
            call_id="cancel-gap",
            family_id="fam-voice",
            store=InMemoryCallRecordStore(),
        )
        bridge = FreeSwitchBridgeSession(
            call_id=session.state.call_id,
            fs_uuid="uuid-cancel-gap",
            on_inbound=_noop,
            uplink_only=False,
            outbound_mode=FreeSwitchOutboundMode.STREAM_AUDIO_JSON,
        )

        async def send_pcm(pcm: bytes) -> None:
            await bridge.enqueue_outbound_pcm(pcm)

        flush_calls: list[None] = []

        async def flush() -> None:
            flush_calls.append(None)

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="fam-voice",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(cancel=_noop),
            llm=SimpleNamespace(),
            media=MediaCallbacks(send_pcm, flush, _noop, _noop),
            config=CallActorConfig(telephony_stream=True, post_speech_pause_ms=0),
        )
        actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)

        ws = _GatedWebSocket()
        actor_pump = asyncio.create_task(actor._playback_pump())
        bridge_pump = asyncio.create_task(bridge._pump_outbound_to_ws(ws))
        try:
            actor._playback.begin_phrase("g-A", "p-A", "Здравствуйте.")
            actor._active_generation = "g-A"
            frame = b"\x01\x00" * 320  # 20ms @ 16k
            assert await actor._playback.enqueue_wait(
                AudioEnvelope(
                    call_id=actor.call_id,
                    generation_id="g-A",
                    phrase_id="p-A",
                    sequence=0,
                    sample_rate=16000,
                    pcm_s16le=frame,
                )
            )
            # Chunk A is now popped from the local queue and blocked inside
            # the downstream send: local cancel can no longer recall it.
            await asyncio.wait_for(ws.send_entered.wait(), timeout=2.0)

            await actor._interrupt_playback(flush=True)
            assert actor._active_generation is None
            await asyncio.sleep(0)
            assert len(flush_calls) == 1

            ws.release.set()
            for _ in range(200):
                if ws.sent_text:
                    break
                await asyncio.sleep(0.01)
            # Cancelled generation still played downstream: the gap.
            assert len(ws.sent_text) == 1
        finally:
            actor._stopped = True
            actor_pump.cancel()
            bridge_pump.cancel()
            await asyncio.gather(actor_pump, bridge_pump, return_exceptions=True)
            await bridge.close()

    asyncio.run(scenario())
