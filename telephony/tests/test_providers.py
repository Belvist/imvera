"""Stage 1/5: provider contract + factory tests.

No network access: the cloud providers only exercise their request-building
and circuit-breaker logic against local fakes, and the factories are checked
to fall back to local backends when no API keys are configured.
"""
import os
import sys
import threading
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

import moss_providers as mp  # noqa: E402


class _FakeTTS:
    """TTSClient duck-API fake."""

    def __init__(self):
        self.generated = []
        self.ready_flag = True

    def ready(self):
        return self.ready_flag

    def generate(self, text):
        self.generated.append(text)
        return b"RIFF" + b"0" * 40  # fake WAV

    def stream(self, text, cancel_event=None, stream_id=None):
        yield {"i": 0, "wav_b64": "QUJD", "done": False}
        yield {"done": True}

    def cancel_stream_by_id(self, stream_id):
        pass


def _clear_keys(env):
    for k in ("OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
        env.pop(k, None)


class FactoryFallbackTests(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("OPENAI_API_KEY", "ELEVENLABS_API_KEY",
                        "MOSS_STT_PROVIDER", "MOSS_LLM_PROVIDER",
                        "MOSS_TTS_PROVIDER")}
        _clear_keys(os.environ)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_defaults_are_local(self):
        self.assertIsInstance(mp.build_stt(), mp.LocalSTTProvider)
        self.assertIsInstance(mp.build_llm(), mp.LocalLLMProvider)
        self.assertIsInstance(mp.build_tts(), mp.LocalTTSProvider)

    def test_cloud_requested_without_keys_falls_back(self):
        os.environ["MOSS_STT_PROVIDER"] = "openai"
        os.environ["MOSS_LLM_PROVIDER"] = "openai"
        os.environ["MOSS_TTS_PROVIDER"] = "elevenlabs"
        self.assertIsInstance(mp.build_stt(), mp.LocalSTTProvider)
        self.assertIsInstance(mp.build_llm(), mp.LocalLLMProvider)
        self.assertIsInstance(mp.build_tts(), mp.LocalTTSProvider)

    def test_cloud_not_ready_without_keys(self):
        self.assertFalse(mp.OpenAISTTProvider().ready())
        self.assertFalse(mp.OpenAILLMProvider().ready())
        self.assertFalse(mp.ElevenLabsTTSProvider().ready())


class CircuitBreakerTests(unittest.TestCase):
    def test_trips_after_threshold(self):
        b = mp._Breaker(threshold=3, cooldown=60)
        for _ in range(3):
            b.failed()
        with self.assertRaises(mp.ProviderCircuitOpen):
            b.guard()

    def test_success_resets(self):
        b = mp._Breaker(threshold=3, cooldown=60)
        b.failed()
        b.failed()
        b.succeeded()
        b.failed()
        b.failed()  # only 2 consecutive -> still closed
        b.guard()   # must not raise


class ProviderErrorBehaviourTests(unittest.TestCase):
    def test_openai_stt_requires_key(self):
        with self.assertRaises(mp.ProviderError):
            mp.OpenAISTTProvider(api_key="").transcribe(b"RIFF" + b"\x00" * 44)

    def test_openai_llm_requires_key(self):
        with self.assertRaises(mp.ProviderError):
            mp.OpenAILLMProvider(api_key="").chat(
                [{"role": "user", "content": "x"}])

    def test_elevenlabs_requires_key(self):
        with self.assertRaises(mp.ProviderError):
            mp.ElevenLabsTTSProvider(api_key="", voice_id="").synthesize("x")

    def test_local_stt_breaker_opens_on_outage(self):
        p = mp.LocalSTTProvider(host="127.0.0.1", port=1)  # nothing listens
        for _ in range(3):
            try:
                p.transcribe(b"RIFF" + b"\x00" * 44)
            except mp.ProviderError:
                pass
        with self.assertRaises(mp.ProviderCircuitOpen):
            p.transcribe(b"RIFF" + b"\x00" * 44)


class TTSContractDefaultStreamTests(unittest.TestCase):
    def test_default_stream_wraps_synthesize(self):
        import base64

        class _Synth(mp.TTSProvider):
            def ready(self):
                return True

            def synthesize(self, text):
                return b"RIFFfake"

        frames = list(_Synth().stream("hello"))
        self.assertEqual(frames[0]["i"], 0)
        self.assertEqual(base64.b64decode(frames[0]["wav_b64"]), b"RIFFfake")
        self.assertTrue(frames[-1].get("done"))

    def test_default_stream_handles_none(self):
        class _Synth(mp.TTSProvider):
            def ready(self):
                return True

            def synthesize(self, text):
                return None

        frames = list(_Synth().stream("hello"))
        self.assertEqual(frames, [{"done": True}])


class CloudTTSAdapterTests(unittest.TestCase):
    def test_pcm_wrapped_into_wav(self):
        class _P(mp.TTSProvider):
            def ready(self):
                return True

            def synthesize(self, text):
                return b"\x00\x01" * 100  # raw PCM, no RIFF header

        class _Local(mp.LocalTTSProvider):
            def __init__(self):
                engine = _FakeTTS()
                super().__init__(engine=engine)

        from call_agent import CloudTTSAdapter, wav_to_pcm
        adapter = CloudTTSAdapter(_P())
        wav = adapter.generate("hi")
        self.assertTrue(wav.startswith(b"RIFF"))
        pcm, rate = wav_to_pcm(wav)
        self.assertEqual(rate, CloudTTSAdapter.PCM_RATE)
        self.assertTrue(pcm)

    def test_stream_respects_cancel(self):
        import base64

        class _P(mp.TTSProvider):
            def ready(self):
                return True

            def synthesize(self, text):
                return b"RIFF" + b"\x00" * 20

            def stream(self, text, cancel_event=None, stream_id=None):
                for i in range(5):
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    yield {"i": i, "wav_b64": base64.b64encode(
                        b"RIFF" + b"\x00" * 20).decode(), "done": False}
                yield {"done": True}

        from call_agent import CloudTTSAdapter
        cancel = threading.Event()
        cancel.set()  # barge-in before the first frame
        frames = list(CloudTTSAdapter(_P()).stream("x", cancel_event=cancel))
        self.assertEqual(frames, [])


class CloudLLMAdapterTests(unittest.TestCase):
    def test_chat_returns_none_on_error(self):
        from call_agent import CloudLLMAdapter

        class _P(mp.LLMProvider):
            def ready(self):
                return True

            def chat(self, messages, max_tokens=120, temp=0.65, timeout=30):
                raise mp.ProviderError("boom")

        self.assertIsNone(CloudLLMAdapter(_P()).chat([]))


class SessionStoreTests(unittest.TestCase):
    def test_memory_roundtrip(self):
        store = mp.MemorySessionStore()
        doc = mp.session_doc("c1", dialogue_step=3, last_intent="retention")
        self.assertIsNone(store.get("c1"))
        store.put("c1", doc)
        got = store.get("c1")
        self.assertEqual(got["dialogue_step"], 3)
        self.assertEqual(got["last_intent"], "retention")
        store.put("c1", mp.session_doc("c1", dialogue_step=4))
        self.assertEqual(store.get("c1")["dialogue_step"], 4)
        store.delete("c1")
        self.assertIsNone(store.get("c1"))

    def test_memory_ttl_expires(self):
        store = mp.MemorySessionStore(default_ttl_seconds=0)
        store.put("c1", mp.session_doc("c1"), ttl_seconds=1)
        self.assertIsNotNone(store.get("c1"))
        time.sleep(1.05)
        self.assertIsNone(store.get("c1"))

    def test_memory_defensive_copy(self):
        store = mp.MemorySessionStore()
        doc = mp.session_doc("c1")
        store.put("c1", doc)
        got = store.get("c1")
        got["summary"] = "mutated"
        self.assertEqual(store.get("c1")["summary"], "")

    def test_session_doc_schema(self):
        doc = mp.session_doc("c1", worker_id="w1", customer_id="u9")
        for k, t in mp.SESSION_STATE_SCHEMA.items():
            self.assertIn(k, doc, k)
            self.assertIsInstance(doc[k], t, k)
        self.assertEqual(doc["worker_id"], "w1")

    def test_redis_store_lazy_import_fails_without_package(self):
        try:
            import redis  # noqa: F401
        except ImportError:
            with self.assertRaises(RuntimeError):
                mp.RedisSessionStore(url="redis://127.0.0.1:1/0")
            return
        self.skipTest("redis package present")

    def test_factory_defaults_to_memory(self):
        store = mp.build_session_store(prefer="memory")
        self.assertIsInstance(store, mp.MemorySessionStore)

    def test_factory_falls_back_on_redis_unavailable(self):
        store = mp.build_session_store(prefer="redis",
                                       url="redis://127.0.0.1:1/0")
        self.assertIsInstance(store, mp.MemorySessionStore)


if __name__ == "__main__":
    unittest.main(verbosity=2)
