"""Always-on uplink when idle; half-duplex mute during Vera playback; echo discard."""

import asyncio
from types import SimpleNamespace

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_runtime.audio_channels import extract_client_uplink
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from packages.voice_runtime.playback import PlaybackQueue


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


def test_uplink_muted_during_playback() -> None:
    """While Vera plays, uplink must not reach VAD (echo self-barge-in gate)."""

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
                return True, False

        class _Collector:
            def on_frame(self, _pcm, _started, _ended):
                return None

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="fam-voice",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(cancel=_noop),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        actor._media_ready = True
        actor._vad = _Vad()
        actor._collector = _Collector()
        actor._playback = PlaybackQueue(call_id=actor.call_id)
        actor._playback.begin_phrase("g-vera-speaking", "phrase", "Расскажите...")
        actor._active_generation = "g-vera-speaking"
        actor._render_generation = "g-vera-speaking"
        frame = b"\x00\x01" * 320
        await actor._feed_uplink_pcm(frame)
        assert fed == []
        assert actor._active_generation == "g-vera-speaking"

        actor._active_generation = None
        await actor._feed_uplink_pcm(frame)
        assert fed == [frame]

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
    assert not actor._is_assistant_echo("Да.")
    assert not actor._is_assistant_echo("да")


def test_assistant_echo_prefix_and_in_progress_phrase() -> None:
    """sip-31365dee13: STT 'Сейчас' must match in-progress / interrupted Vera phrase."""
    actor = CallActor(
        call_id="echo-prefix",
        family_id="fam-voice",
        session=CallSession(
            call_id="echo-prefix",
            family_id="fam-voice",
            store=InMemoryCallRecordStore(),
        ),
        stt=SimpleNamespace(),
        tts=SimpleNamespace(),
        llm=SimpleNamespace(),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
    )
    actor._playback = PlaybackQueue(call_id=actor.call_id)
    actor._playback.begin_phrase(
        "g-1",
        "p-1",
        "Сейчас не получилось узнать, как у вас дела.",
    )
    assert actor._is_assistant_echo("Сейчас")
    assert actor._is_assistant_echo("Сейчас не получилось")
    assert not actor._is_assistant_echo("Нормально")
