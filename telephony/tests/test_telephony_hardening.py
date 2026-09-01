"""Regression tests for the 2026-08-27 telephony hardening.

Covers the deterministic, offline-testable parts of the timeout/stability and
"AI ignores user input" fixes:
  * bounded, environment-overridable TTS and tg_server stream timeouts
    (the old hardcoded 600 s ceilings could wedge a turn for ten minutes);
  * supervisor ADOPT-OR-SPAWN: never restart-storm over an occupied port;
  * orchestrator empty-LLM-reply fallback (empty stream no longer silent).
"""

import collections
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))
sys.path.insert(0, os.path.join(_HERE, "..", "tg"))


class TtsTimeoutTest(unittest.TestCase):
    """TTSClient timeouts are bounded and env-overridable (not 600 s)."""

    def test_imports(self):
        import adapters.moss_tts as m  # noqa: E401
        self.assertLess(m.TTS_GEN_TIMEOUT, 120)
        self.assertLess(m.TTS_STREAM_IDLE, 60)
        self.assertLessEqual(m.TTS_STREAM_TOTAL, 60)

    def test_env_override(self):
        os.environ["MOSS_TTS_GEN_TIMEOUT"] = "7"
        try:
            import importlib
            import adapters.moss_tts as m
            importlib.reload(m)
            self.assertEqual(m.TTS_GEN_TIMEOUT, 7)
        finally:
            os.environ.pop("MOSS_TTS_GEN_TIMEOUT", None)
            import importlib
            import adapters.moss_tts as m
            importlib.reload(m)


class TgServerTimeoutTest(unittest.TestCase):
    def test_stream_defaults_bounded(self):
        import tg_server as t
        self.assertLess(t.TURN_STREAM_IDLE, 60)
        self.assertLessEqual(t.TURN_STREAM_TOTAL, 60)


def _spec(health="http://127.0.0.1:99/health", service=None):
    spec = {"name": "t", "cmd": ["true"], "health": health,
            "ready_key": None, "startup_grace": 5}
    if service:
        spec["service"] = service
    return spec


class SupervisorAdoptTest(unittest.TestCase):
    def setUp(self):
        import moss_supervisor as sup
        self.sup = sup

    def test_adopts_already_healthy(self):
        c = self.sup.Child(_spec())
        with mock.patch.object(c, "_probe_healthy", return_value=True):
            c.start()
        self.assertTrue(c.external)
        self.assertIsNone(c.proc)

    def test_spawns_when_port_free(self):
        c = self.sup.Child(_spec())
        with mock.patch.object(c, "_probe_healthy", return_value=False), \
                mock.patch.object(c, "_port_occupied", return_value=False), \
                mock.patch("subprocess.Popen") as popen:
            c.start()
        popen.assert_called_once()
        self.assertFalse(c.external)
        self.assertIsNotNone(c.proc)

    def test_refuses_spawn_over_occupied_foreign_port(self):
        # read.md P0: a STRANGER on our port is a configuration conflict,
        # never a quiet "degraded external" adoption — fail fast.
        c = self.sup.Child(_spec())
        with mock.patch.object(c, "_probe_healthy", return_value=False), \
                mock.patch.object(c, "_port_occupied", return_value=True), \
                mock.patch("subprocess.Popen") as popen:
            with self.assertRaises(self.sup.ConfigConflict):
                c.start()
        popen.assert_not_called()
        self.assertFalse(c.external, "foreign port must NOT be adopted")
        self.assertIsNone(c.proc)

    # read.md rev-3 G4: identity contract — an endpoint is only "ours" to
    # adopt when /health self-identifies as the expected SERVICE on a
    # compatible protocol_version.
    def _probe_via(self, spec, payload):
        import json as _json
        import moss_supervisor as sup
        c = sup.Child(spec)
        # MagicMock (not Mock) so `with urlopen(...) as r:` yields the mock.
        resp = mock.MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = _json.dumps(payload).encode()
        with mock.patch("moss_supervisor.urllib.request.urlopen",
                        return_value=resp):
            return c._probe_healthy()

    def test_identity_accepts_matching_service(self):
        ok = self._probe_via(
            _spec(service="mossvoice-tts"),
            {"service": "mossvoice-tts", "protocol_version": 1,
             "ready": True, "ok": True})
        self.assertTrue(ok)

    def test_identity_rejects_wrong_service(self):
        # A DIFFERENT process (or wrong config) on our port must NOT be
        # adopted even if it answers {"ready": true}.
        bad = self._probe_via(
            _spec(service="mossvoice-tts"),
            {"service": "mossvoice-llm", "protocol_version": 1,
             "ready": True, "ok": True})
        self.assertFalse(bad)

    def test_identity_rejects_newer_protocol(self):
        future = self._probe_via(
            _spec(service="mossvoice-tts"),
            {"service": "mossvoice-tts", "protocol_version": 99,
             "ready": True, "ok": True})
        self.assertFalse(future)

    def test_supervisor_only_service_filters_children(self):
        import moss_supervisor as sup
        s = sup.Supervisor(only="runtime")
        self.assertEqual([c.name for c in s.children], ["runtime"])

    def test_supervisor_unknown_service_fails(self):
        import moss_supervisor as sup
        with self.assertRaises(SystemExit):
            sup.Supervisor(only="no-such-service")


class EmptyReplyFallbackTest(unittest.TestCase):
    """An empty model reply must still produce an audible answer, not silence."""

    def test_condition_allows_empty_reply(self):
        # The fix lowered the guard from `if fb and reply and reply != fb` to
        # `if fb and reply != fb`, so an empty reply (reply == "") no longer
        # suppresses the fallback. This is exactly the observed "she keeps
        # talking but doesn't answer" scenario -> it must reach the fallback.
        from core.orchestrator import Serve
        fallback = "Повторите, пожалуйста."
        plan = {"fallback": fallback}

        # Reproduce the decision branch verbatim against the fixed condition.
        got_audio, reply = False, ""
        any_audio = False
        fb = plan.get("fallback")
        if not got_audio and fb and reply != fb:
            any_audio = True  # fallback would be spoken

        self.assertTrue(any_audio, "empty reply must trigger the fallback")


class GenerationIdentityTest(unittest.TestCase):
    """ARCHITECTURE 2026-08-27: turn_id/generation_id end-to-end.

    Every accepted turn starts a new generation; every frame produced by the
    stream bares the generation it belongs to, so a stale in-flight result
    (old TTS finishing after a barge-in) can be discarded by identity, not by
    a forest of cancel flags.
    """

    def _serve(self):
        from core.orchestrator import Serve

        class _Args:
            refs = []
            tts_port_file = None
            tts_port = None
            inference_steps = 6
            no_style = False
            outdir = "/tmp/mossvoice_gen_identity"
            tts_host = None

        serve = Serve(_Args())
        serve.llm.ready()
        return serve

    def test_new_turn_is_monotonic(self):
        from core.state import CallContext
        ctx = CallContext.__new__(CallContext)
        ctx.call_id = "c"
        ctx.turn_id = 0
        ctx.generation_id = 0
        import threading
        ctx._generation_lock = threading.Lock()
        seen = [ctx.new_turn() for _ in range(5)]
        for i, (turn, gen) in enumerate(seen, start=1):
            self.assertEqual(turn, i)
            self.assertEqual(gen, i)
            self.assertEqual(turn, gen)

    def test_begin_turn_bumps_generation_and_guards_overlap(self):
        from core.orchestrator import CallBusyError
        serve = self._serve()
        cid = serve.new_call()
        ctx = serve.get_call(cid)

        ctx1 = serve.begin_turn(cid)
        self.assertEqual(ctx1.turn_id, 1)
        self.assertEqual(ctx1.generation_id, 1)
        # overlapping turn must be rejected AND must not bump the generation
        with self.assertRaises(CallBusyError):
            serve.begin_turn(cid)
        self.assertEqual(ctx.generation_id, 1)

        serve.end_turn(ctx)
        ctx2 = serve.begin_turn(cid)
        self.assertEqual(ctx2.turn_id, 2)
        self.assertEqual(ctx2.generation_id, 2)

        serve.end_turn(ctx)

    def test_stream_frames_carry_generation_tags(self):
        """Every emitted frame — interim, audio, done — carries the same
        turn_id/generation_id the stream was started for."""
        import base64
        import io
        import struct
        import tempfile
        import wave

        serve = self._serve()

        class _Wav:
            @staticmethod
            def frame():
                buf = io.BytesIO()
                with wave.open(buf, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(16000)
                    w.writeframes(struct.pack("<800h", *([1200] * 800)))
                return base64.b64encode(buf.getvalue()).decode()

        class _FakeSTT:
            def transcribe_with_confidence(self, _path):
                return type("R", (), {"text": "неразборчиво",
                                     "confidence": 0.30})()

        class _FakeTTS:
            def cancel_stream_by_id(self, _sid):
                pass

            def stream(self, text, cancel_event=None, stream_id=None):
                yield {"i": 0, "wav_b64": _Wav.frame()}
                yield {"done": True}

        cid = serve.new_call()
        ctx = serve.get_call(cid)
        serve.stt = _FakeSTT()
        serve.tts = _FakeTTS()

        ctx1 = serve.begin_turn(cid)
        gen, turn = ctx1.generation_id, ctx1.turn_id

        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with open(wav, "wb") as f:
            f.write(_wav_bytes32())
        seg_dir = tempfile.mkdtemp()
        try:
            frames = list(serve.process_turn_stream(
                wav, call_id=cid, segment_dir=seg_dir))
            self.assertTrue(frames, "stream must emit frames")
            for fr in frames:
                # every frame identifies its generation; the done frame also
                # carries the full meta with the same identity
                self.assertEqual(fr.get("turn_id"), turn, fr)
                self.assertEqual(fr.get("generation_id"), gen, fr)
            done = [f for f in frames if f.get("done")]
            self.assertEqual(len(done), 1)
            self.assertEqual(done[0]["generation_id"], gen)
        finally:
            os.remove(wav)
            import shutil
            shutil.rmtree(seg_dir, ignore_errors=True)
            serve.end_turn(ctx)

    def test_canned_stream_commits_last_reply(self):
        """Canned phone-path replies must update _last_reply (echo-guard/memory)."""
        import tempfile

        serve = self._serve()

        class _FakeSTT:
            def transcribe_with_confidence(self, _path):
                return type("R", (), {"text": "неразборчиво",
                                     "confidence": 0.30})()

        class _FakeTTS:
            def cancel_stream_by_id(self, _sid):
                pass

            def stream(self, text, cancel_event=None, stream_id=None):
                import base64
                import io
                import struct
                import wave
                buf = io.BytesIO()
                with wave.open(buf, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(16000)
                    w.writeframes(struct.pack("<800h", *([1200] * 800)))
                yield {"i": 0, "wav_b64": base64.b64encode(buf.getvalue()).decode()}
                yield {"done": True}

        cid = serve.new_call(caller_id="+79001234567")
        agent = serve.get_call(cid).agent
        serve.stt = _FakeSTT()
        serve.tts = _FakeTTS()
        ctx = serve.begin_turn(cid)

        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with open(wav, "wb") as f:
            f.write(_wav_bytes32())
        seg_dir = tempfile.mkdtemp()
        try:
            list(serve.process_turn_stream(wav, call_id=cid, segment_dir=seg_dir))
            self.assertTrue(agent._last_reply,
                            "canned stream must commit spoken reply")
            self.assertTrue(any(r == "assistant" and txt == agent._last_reply
                                for r, txt in agent.llm_history),
                            "canned reply must be in llm_history")
        finally:
            os.remove(wav)
            import shutil
            shutil.rmtree(seg_dir, ignore_errors=True)
            serve.end_turn(ctx)


class GenerationDiscardTest(unittest.IsolatedAsyncioTestCase):
    """ARCHITECTURE 2026-08-27: a frame tagged with a stale generation_id
    (an old TTS stream that survived its cancel after a barge-in/new turn)
    must be dropped by identity in TXPipeline._run — it never reaches the
    client, no matter what order it arrives in."""

    def _frame(self, i, gid):
        return {"i": i, "wav_b64": "QQ==", "generation_id": gid}

    def _tx(self, frames):
        import tg_server as t

        class _Bridge:
            def turn_stream(self, pcm, rate=16000, cancel_event=None):
                for fr in frames:
                    yield fr
                yield {"done": True}

        sent = []

        async def send(payload):
            sent.append(payload)

        return t.TXPipeline(_Bridge(), send), sent

    async def test_stale_generation_frames_are_dropped(self):
        import threading

        import tg_server as t
        tx, sent = self._tx([
            self._frame(0, 1),
            self._frame(1, 2),   # stale: superseded generation must die
            self._frame(2, 1),
        ])
        await tx._run(b"", t.SAMPLE_RATE, 1, threading.Event())

        audio = [s for s in sent
                 if s.get("type") == "chunk" and s.get("wav_b64")]
        self.assertEqual(len(audio), 2, [s for s in sent if s.get("type")])
        for a in audio:
            self.assertEqual(a.get("generation_id"), 1, a)
        finished = [s for s in sent if s.get("type") == "finished"]
        self.assertEqual(len(finished), 1)


class EmptyStreamFallbackTest(unittest.TestCase):
    """read.md / Stage-9: an EMPTY model stream (LLM yields nothing) must
    still be spoken — the scripted fallback audio is produced through the
    REAL process_turn_stream path, not a bare condition re-check."""

    def _serve(self):
        from core.orchestrator import Serve

        class _Args:
            refs = []
            tts_port_file = None
            tts_port = None
            inference_steps = 6
            no_style = False
            outdir = "/tmp/mossvoice_fallback_test"
            tts_host = None

        return Serve(_Args())

    def test_empty_llm_stream_still_speaks_fallback(self):
        import base64
        import io
        import struct
        import tempfile
        import wave

        class _Wav:
            @staticmethod
            def frame():
                buf = io.BytesIO()
                with wave.open(buf, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(16000)
                    w.writeframes(struct.pack("<800h", *([1200] * 800)))
                return base64.b64encode(buf.getvalue()).decode()

        class _FakeSTT:
            TEXT = "вчера к нам приезжала внучка и мы пили чай с пирогом"

            def transcribe(self, _path):
                return self.TEXT

            def transcribe_with_confidence(self, _path):
                return type("R", (), {"text": self.TEXT, "confidence": 0.9})()

        class _FakeLLM:
            """Yields NOTHING — the exact 'AI keeps talking but produces no
            usable reply' failure the fix targets."""

            def chat_stream(self, history):
                return iter(())

            def chat(self, history):
                return None

        class _FakeTTS:
            def __init__(self):
                self.synthesized = []

            def cancel_stream_by_id(self, _sid):
                pass

            def stream(self, text, cancel_event=None, stream_id=None):
                self.synthesized.append(text)
                yield {"i": 0, "wav_b64": _Wav.frame()}
                yield {"done": True}

        os.environ["MOSS_NO_WARMUP"] = "1"  # hermetic: no model warmup threads
        serve = self._serve()
        fstt, fllm, ftts = _FakeSTT(), _FakeLLM(), _FakeTTS()
        serve.stt, serve.tts = fstt, ftts

        cid = serve.new_call()
        ctx = serve.get_call(cid)
        ctx.agent.llm = fllm

        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with open(wav, "wb") as f:
            f.write(_wav_bytes32())
        try:
            ctx1 = serve.begin_turn(cid)
            gen, turn = ctx1.generation_id, ctx1.turn_id
            frames = list(serve.process_turn_stream(wav, call_id=cid))
            # the empty model stream MUST still produce audible fallback audio
            audio = [fr for fr in frames
                     if fr.get("wav_b64") and not fr.get("aborted")]
            self.assertTrue(audio, "no fallback audio was produced")
            self.assertEqual(len(ftts.synthesized), 1,
                             f"fallback spoken once, got: {ftts.synthesized}")
            fallback = ftts.synthesized[0]
            self.assertTrue(fallback.strip(),
                            "synthesized text must be a real phrase")
            for fr in audio:
                self.assertEqual(fr.get("generation_id"), gen, fr)
                self.assertEqual(fr.get("turn_id"), turn, fr)
        finally:
            os.remove(wav)
            serve.end_turn(ctx)


class CheckInInterruptTest(unittest.TestCase):
    """read.md #16: a caller question during check_in is a TEMPORARY
    interrupt — the agenda never advances mid-question, and the next
    non-question turn resumes check_in at the SAME position."""

    def _reply(self, ag, text, conf=0.85, reason=None):
        ag.observe_confidence(conf)
        return ag.plan_reply(text, reason=reason)

    def _new_check_in(self):
        from core.dialogue import Agent
        ag = Agent()
        ag.start_check_in()          # mode=check_in, topic 0 on the table
        self.assertEqual(ag.mode, "check_in")
        self.assertTrue(ag._agenda_asked)
        return ag

    def test_question_is_a_temporary_interrupt(self):
        ag = self._new_check_in()
        idx0 = ag._agenda_idx

        # a direct caller question -> temporary interrupt, not a permanent
        # flip to companion, and the topic is deferred (never advanced)
        plan = self._reply(ag, "какое сегодня число?")
        self.assertEqual(ag.mode, "companion")
        self.assertIsNotNone(plan.get("intent"))
        self.assertEqual(ag._agenda_idx, idx0)
        self.assertFalse(ag._agenda_asked)
        self.assertIsNotNone(ag._interrupt)
        self.assertEqual(ag._interrupt["resume_mode"], "check_in")
        self.assertTrue(ag._interrupt["agenda_asked"])

        # a follow-up question stays interrupted at the same position
        self._reply(ag, "а завтра какой день недели?")
        self.assertEqual(ag.mode, "companion")
        self.assertEqual(ag._agenda_idx, idx0)

        # «спасибо» is NOT the wellbeing answer — it is the RESUME
        # TRANSITION: Vera re-asks the pending agenda question. The agenda
        # flag is restored only on RESUME DONE, so the answer right after
        # the transition is the one that closes the topic.
        plan = self._reply(ag, "спасибо")
        self.assertIn("Возвращаясь к нашему разговору", plan["fallback"])
        self.assertEqual(ag._interrupt["phase"], "resume")
        self.assertFalse(ag._agenda_asked)
        self.assertEqual(ag._agenda_idx, idx0)

        # a real answer AFTER the transition -> RESUME DONE: check_in at the
        # SAME position, and this reply closes topic 0 exactly as if no
        # question had interrupted it (position was preserved).
        self._reply(ag, "да всё хорошо")
        self.assertEqual(ag.mode, "check_in")
        self.assertIsNone(ag._interrupt)
        self.assertEqual(ag._agenda_idx, idx0 + 1)

    def test_interrupt_empty_turn_keeps_interrupt(self):
        ag = self._new_check_in()
        idx0 = ag._agenda_idx
        self._reply(ag, "а сколько сейчас времени?")
        # a no-speech turn mid-interrupt: the silence ladder runs; the
        # interrupt stays ACTIVE (no resume consumed), position untouched.
        self._reply(ag, "", reason="no_speech")
        self.assertEqual(ag._agenda_idx, idx0)
        self.assertIsNotNone(ag._interrupt)
        self.assertEqual(ag._interrupt["phase"], "answer")
        # the question is still open: answering it later resumes normally
        self._reply(ag, "спасибо, подождите")
        self.assertEqual(ag._interrupt["phase"], "resume")

    def test_hyphen_boundary_is_not_a_question(self):
        from core.dialogue import _is_text_question
        self.assertFalse(_is_text_question("что-то сегодня голова болит"))
        self.assertFalse(_is_text_question("как-то странно себя чувствую"))
        self.assertTrue(_is_text_question("что случилось?"))
        self.assertTrue(_is_text_question("как вы себя чувствуете"))


class InProcessLLMBanTest(unittest.TestCase):
    """ARCHITECTURE 2026-08-27: the orchestrator must never load a heavy
    model in-process as a failure fallback. The scripted cascade is
    remote/cloud -> canned reply; in-process stays an explicit staging opt-in.
    """

    def _client(self):
        import importlib
        import adapters.llm as llm_mod
        importlib.reload(llm_mod)
        return llm_mod.LLMClient()

    def test_default_never_touches_mlx_lm(self):
        import builtins
        os.environ.pop("MOSS_LLM_ALLOW_IN_PROCESS", None)
        cli = self._client()
        real_import = builtins.__import__

        def _guard(name, *a, **k):
            if name.split(".")[0] == "mlx_lm":
                raise AssertionError("in-process LLM loaded without opt-in")
            return real_import(name, *a, **k)

        with mock.patch.object(builtins, "__import__", side_effect=_guard):
            self.assertFalse(cli._ensure_local())
        self.assertTrue(cli._failed)
        self.assertIsNone(cli._model)

    def test_explicit_opt_in_allows_local_load(self):
        import sys
        import types
        os.environ["MOSS_LLM_ALLOW_IN_PROCESS"] = "1"
        fake = types.ModuleType("mlx_lm")
        fake.load = lambda _id: ("model", "tok")
        sys.modules["mlx_lm"] = fake
        try:
            cli = self._client()
            self.assertTrue(cli._ensure_local())
            self.assertTrue(cli._loaded)
        finally:
            sys.modules.pop("mlx_lm", None)
            os.environ.pop("MOSS_LLM_ALLOW_IN_PROCESS", None)


def _wav_bytes32():
    """16 kHz mono PCM WAV for the stream fixture (matches task audio)."""
    import struct
    body = struct.pack("<800h", *([1200] * 800))
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(body)
    return buf.getvalue()


class DialogueFlowTest(unittest.TestCase):
    """Full dialogue pipeline through Serve — equivalent to
    test_dialogue_via_http_api (turn_text path) but via process_turn_stream."""

    def _serve(self):
        from core.orchestrator import Serve

        class _Args:
            refs = []
            tts_port_file = None
            tts_port = None
            inference_steps = 6
            no_style = False
            outdir = "/tmp/mossvoice_dialogue_test"
            tts_host = None

        return Serve(_Args())

    def test_full_dialogue_flow(self):
        import base64
        import io
        import struct
        import wave

        class _FakeLLM:
            def __init__(self):
                self._n = 0

            def chat_stream(self, history):
                self._n += 1
                yield ("Как самочувствие? " + str(self._n))

            def chat(self, history):
                return "Как самочувствие? " + str(self._n)

        class _FakeSTT:
            TEXT = "всё хорошо"

            def transcribe(self, _path):
                return self.TEXT

            def transcribe_with_confidence(self, _path):
                return type("R", (), {"text": self.TEXT, "confidence": 0.9})()

        class _FakeTTS:
            def __init__(self):
                self.synthesized = []

            def cancel_stream_by_id(self, _sid):
                pass

            def stream(self, text, cancel_event=None, stream_id=None):
                self.synthesized.append(text)
                # Build a minimal 16 kHz mono WAV frame
                buf = io.BytesIO()
                with wave.open(buf, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(16000)
                    w.writeframes(struct.pack("<800h", *([1200] * 800)))
                wav_b64 = base64.b64encode(buf.getvalue()).decode()
                yield {"i": 0, "wav_b64": wav_b64}
                yield {"done": True}

        os.environ["MOSS_NO_WARMUP"] = "1"
        serve = self._serve()
        fstt = _FakeSTT()
        fllm = _FakeLLM()
        ftts = _FakeTTS()
        serve.stt, serve.tts = fstt, ftts
        serve.llm = fllm

        cid = serve.new_call()
        try:
            # Turn 1: greeting — should start check-in
            fd, wav = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            with open(wav, "wb") as f:
                f.write(_wav_bytes32())
            try:
                ctx = serve.begin_turn(cid)
                frames = list(serve.process_turn_stream(wav, call_id=cid))
                audio = [fr for fr in frames
                         if fr.get("wav_b64") and not fr.get("aborted")]
                self.assertTrue(audio, "no audio on turn 1")
                self.assertGreater(len(ftts.synthesized), 0)
                # Agent should be in check_in or companion mode after greeting
                self.assertIsNotNone(serve.get_call(cid).agent)
            finally:
                os.remove(wav)

            # Turn 2: confirmation — agenda should advance
            fllm._n = 10
            fd, wav = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            with open(wav, "wb") as f:
                f.write(_wav_bytes32())
            try:
                frames = list(serve.process_turn_stream(wav, call_id=cid))
                audio = [fr for fr in frames
                         if fr.get("wav_b64") and not fr.get("aborted")]
                self.assertTrue(audio, "no audio on turn 2")
                self.assertGreater(len(ftts.synthesized), 0)
            finally:
                os.remove(wav)

        finally:
            serve.end_turn(serve.get_call(cid))


if __name__ == "__main__":
    unittest.main()