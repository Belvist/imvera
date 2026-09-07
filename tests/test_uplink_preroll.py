"""Always-on uplink and stereo LEFT=caller demux."""

import asyncio
from types import SimpleNamespace

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_runtime.audio_channels import extract_client_uplink
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks


async def _noop(*_a, **_k):
    return None


def test_extract_client_uplink_stereo_left_only() -> None:
    stereo = b"".join(
        (left.to_bytes(2, "little", signed=True) + right.to_bytes(2, "little", signed=True))
        for left, right in ((100, 9000), (200, 8000), (-50, 7000))
    )
    mono = extract_client_uplink(stereo, channels=2)
    import array

    samples = array.array("h")
    samples.frombytes(mono)
    assert list(samples) == [100, 200, -50]


def test_uplink_ignored_during_playback() -> None:
    """Client PCM is dropped during TTS so Vera's voice is not fed to STT as echo."""

    async def scenario() -> None:
        session = CallSession(
            call_id="duplex-test",
            family_id="fam-voice",
            store=InMemoryCallRecordStore(),
        )
        fed: list[bytes] = []

        class _Vad:
            def feed(self, pcm: bytes) -> tuple[bool, bool]:
                fed.append(pcm)
                return False, False

        class _Collector:
            def on_frame(self, _pcm, _started, _ended):
                return None

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="fam-voice",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        actor._media_ready = True
        actor._vad = _Vad()
        actor._collector = _Collector()
        actor._active_generation = "g-vera-speaking"
        frame = b"\x00\x01" * 320
        await actor._feed_uplink_pcm(frame)
        assert fed == []
        assert len(actor._playback_uplink_buf) == 0

    asyncio.run(scenario())


def test_assistant_echo_discarded() -> None:
    actor = CallActor(
        call_id="echo-test",
        family_id="fam-voice",
        session=CallSession(
            call_id="echo-test",
            family_id="fam-voice",
            store=InMemoryCallRecordStore(),
        ),
        stt=SimpleNamespace(),
        tts=SimpleNamespace(),
        llm=SimpleNamespace(),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
    )
    actor._delivered_phrases.append("Я разговариваю с Даниил?")
    assert actor._is_assistant_echo("Я разговариваю с Даниил. Я разговариваю с Даниил.")
    assert not actor._is_assistant_echo("Да, это я")
