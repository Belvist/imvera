"""Always-on uplink when idle; half-duplex mute during Vera playback; echo discard."""

import asyncio
from types import SimpleNamespace

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_runtime.audio import AudioEnvelope
from packages.voice_runtime.audio_channels import extract_client_uplink
from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks
from packages.voice_runtime.lab_half_duplex import (
    apply_lab_half_duplex_env,
    lab_half_duplex_enabled,
    post_speech_pause_ms,
)
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


def test_lab_half_duplex_defaults(monkeypatch) -> None:
    monkeypatch.delenv("IMVERA_LAB_HALF_DUPLEX", raising=False)
    monkeypatch.delenv("IMVERA_POST_SPEECH_PAUSE_MS", raising=False)
    assert lab_half_duplex_enabled() is True
    assert post_speech_pause_ms() == 400
    env = apply_lab_half_duplex_env({})
    assert env["IMVERA_LAB_HALF_DUPLEX"] == "1"
    assert env["IMVERA_POST_SPEECH_PAUSE_MS"] == "400"


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
            config=CallActorConfig(lab_half_duplex=True, post_speech_pause_ms=400),
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


def test_unmute_only_after_post_speech_pause() -> None:
    """Friend pattern: after drain, mic stays muted until post-speech pause elapses."""

    async def scenario() -> None:
        session = CallSession(
            call_id="pause-test",
            family_id="fam-voice",
            store=InMemoryCallRecordStore(),
        )
        fed: list[bytes] = []
        clock = {"t": 1000.0}
        stages: list[str] = []

        class _Vad:
            def feed(self, pcm: bytes) -> tuple[bool, bool]:
                fed.append(pcm)
                return False, False

        class _Collector:
            def on_frame(self, _pcm, _started, _ended):
                return None

        async def emit(event) -> None:
            payload = event.payload or {}
            if payload.get("stage"):
                stages.append(str(payload["stage"]))

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="fam-voice",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(cancel=_noop),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, emit, finish=_noop),
            config=CallActorConfig(lab_half_duplex=True, post_speech_pause_ms=300),
        )
        actor._monotonic = lambda: clock["t"]
        actor._media_ready = True
        actor._vad = _Vad()
        actor._collector = _Collector()
        actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
        actor._playback.begin_phrase("g-done", "p1", "Как вы себя чувствуете?")
        actor._active_generation = "g-done"
        env = AudioEnvelope(
            call_id=actor.call_id,
            generation_id="g-done",
            phrase_id="p1",
            sequence=0,
            sample_rate=16000,
            pcm_s16le=b"\x01\x00" * 320,
        )
        assert await actor._playback.enqueue_wait(env)
        actor._playback.mark_generation_done("success")
        popped = actor._playback.pop_nowait()
        assert popped is not None
        assert actor._playback.playback_complete()

        frame = b"\x02\x00" * 320
        finalize = asyncio.create_task(actor._finalize_turn_playback())
        await asyncio.sleep(0)
        # Still in post-speech pause — uplink must stay discarded.
        assert actor._listen_gated_until is not None
        assert actor._active_generation is None
        await actor._feed_uplink_pcm(frame)
        assert fed == [], "Uplink must stay muted during post-speech pause"

        clock["t"] = actor._listen_gated_until + 0.001
        await finalize
        assert "listen.enabled" in stages
        assert actor._listen_gated_until is None
        assert not actor._uplink_listen_blocked()
        await actor._feed_uplink_pcm(frame)
        assert fed == [frame], "After pause, uplink must reach VAD"

        # Second finalize must not re-mute.
        await actor._finalize_turn_playback()
        assert not actor._uplink_listen_blocked()

    asyncio.run(scenario())


def test_force_unmute_if_pause_cancelled() -> None:
    """Cancelled post-speech pause must still clear listen gate (no permanent deaf)."""

    async def scenario() -> None:
        session = CallSession(
            call_id="cancel-pause",
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
            tts=SimpleNamespace(cancel=_noop),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop, finish=_noop),
            config=CallActorConfig(lab_half_duplex=True, post_speech_pause_ms=5000),
        )
        actor._media_ready = True
        actor._vad = _Vad()
        actor._collector = _Collector()
        actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
        actor._playback.begin_phrase("g-c", "p1", "Алло")
        actor._active_generation = "g-c"
        env = AudioEnvelope(
            call_id=actor.call_id,
            generation_id="g-c",
            phrase_id="p1",
            sequence=0,
            sample_rate=16000,
            pcm_s16le=b"\x01\x00" * 320,
        )
        assert await actor._playback.enqueue_wait(env)
        actor._playback.mark_generation_done("success")
        actor._playback.pop_nowait()

        task = asyncio.create_task(actor._finalize_turn_playback())
        await asyncio.sleep(0.02)
        assert actor._active_generation is None
        assert actor._listen_gated_until is not None
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        # finally on enable path must clear gate
        assert actor._listen_gated_until is None
        assert not actor._uplink_listen_blocked()
        frame = b"\x03\x00" * 320
        await actor._feed_uplink_pcm(frame)
        assert fed == [frame]

    asyncio.run(scenario())


def test_synthetic_echo_during_playback_does_not_self_interrupt() -> None:
    """Echo of Vera's phrase while TTS active must not start speech / barge-in."""

    async def scenario() -> None:
        session = CallSession(
            call_id="echo-barge",
            family_id="fam-voice",
            store=InMemoryCallRecordStore(),
        )
        speech_events: list[str] = []

        async def emit(event):
            speech_events.append(event.event_type.value)

        class _Vad:
            def feed(self, pcm: bytes) -> tuple[bool, bool]:
                # Would fire if uplink were fed — must never be called during playback.
                raise AssertionError("VAD must not see uplink during Vera playback")

        class _Collector:
            def on_frame(self, _pcm, _started, _ended):
                raise AssertionError("collector must not run during Vera playback")

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="fam-voice",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(cancel=_noop),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, emit),
            config=CallActorConfig(lab_half_duplex=True, post_speech_pause_ms=400),
        )
        actor._media_ready = True
        actor._vad = _Vad()
        actor._collector = _Collector()
        actor._playback = PlaybackQueue(call_id=actor.call_id)
        actor._playback.begin_phrase(
            "g-echo",
            "p1",
            "Сейчас не получилось узнать, как у вас дела.",
        )
        actor._active_generation = "g-echo"
        # Synthetic softphone echo of Vera's own greeting.
        loud_echo = b"\x7f\x00" * 320
        await actor._on_pcm(loud_echo, 16000)
        assert actor._active_generation == "g-echo"
        assert "speech.started" not in speech_events
        assert "playback.interrupted" not in speech_events

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
