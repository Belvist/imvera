"""Qwen GGUF provider: routing, fallback, contract-shape (hermetic).

Live-server synthesis is proven separately by bench wav + TTFA probe
(.run/qwen_bench); these tests pin the wiring, never the model.
"""

from __future__ import annotations

import queue

import pytest

from services.tts import qwen_gguf
from services.tts.qwen_gguf import QWEN_SAMPLE_RATE

pytestmark = pytest.mark.tts_provider


def test_sample_rate_is_24k() -> None:
    assert QWEN_SAMPLE_RATE == 24000


def test_voice_default_vera_kseniya() -> None:
    assert qwen_gguf.qwen_voice({}) == "vera_kseniya"


def test_ensure_registers_from_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    d = tmp_path / "models"
    d.mkdir()
    (d / "vera_kseniya.spk").write_bytes(b"spk")
    (d / "vera_kseniya.rvq").write_bytes(b"rvq")
    (d / "vera_kseniya_ref.txt").write_text("Здравствуйте.")
    monkeypatch.setenv("IMVERA_QWEN_GGUF_DIR", str(d))
    monkeypatch.setattr(qwen_gguf, "list_voices", lambda *a, **k: [])
    seen: dict = {}

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout=None):
        seen["url"] = req.full_url
        return FakeResp()

    monkeypatch.setattr(qwen_gguf.urllib.request, "urlopen", fake_open)
    assert qwen_gguf.ensure_voice_registered() is True
    assert seen["url"].endswith("/v1/audio/voices")


def test_ensure_skips_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qwen_gguf, "list_voices", lambda *a, **k: ["vera_kseniya"])
    assert qwen_gguf.ensure_voice_registered() is True


def test_ping_false_on_dead_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_QWEN_TTS_URL", "http://127.0.0.1:9")
    assert qwen_gguf.ping(timeout_s=0.5) is False


def test_synthesize_raises_on_dead_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_QWEN_TTS_URL", "http://127.0.0.1:9")
    with pytest.raises(RuntimeError):
        list(
            qwen_gguf.synthesize_stream(
                "Здравствуйте.", cfg={}, voice="serena", lang="Russian"
            )
        )


def test_worker_routes_qwen_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.tts.worker as worker

    seen: dict = {}

    def fake_qwen(req, out_q, tts_cfg):
        seen["called"] = True
        out_q.put(None)
        return 1

    monkeypatch.setenv("IMVERA_TTS_ENGINE", "qwen_gguf")
    monkeypatch.setattr(worker, "_produce_qwen_chunks", fake_qwen)
    out_q: queue.Queue = queue.Queue()
    req = worker.SynthesizeRequest(
        call_id="t", generation_id="g", phrase_id="p", text="Здравствуйте."
    )
    worker._produce_chunks(req, out_q)
    assert seen.get("called") is True


def test_worker_falls_back_to_silero_on_qwen_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.tts.worker as worker

    calls = []

    def fake_qwen(req, out_q, tts_cfg):
        calls.append("qwen")
        raise RuntimeError("server down")

    def fake_silero(req, out_q, tts_cfg):
        calls.append("silero")
        out_q.put(None)

    monkeypatch.setenv("IMVERA_TTS_ENGINE", "qwen_gguf")
    monkeypatch.setattr(worker, "_produce_qwen_chunks", fake_qwen)
    monkeypatch.setattr(worker, "_produce_silero_chunks", fake_silero)
    out_q: queue.Queue = queue.Queue()
    req = worker.SynthesizeRequest(
        call_id="t", generation_id="g", phrase_id="p", text="Здравствуйте."
    )
    worker._produce_chunks(req, out_q)
    assert calls == ["qwen", "silero"]


def test_qwen_phrase_cache_serves_repeat_without_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.tts.worker as worker

    worker._QWEN_PHRASE_CACHE.clear()
    calls = []

    def fake_stream(text, **kw):
        calls.append(text)
        yield b"\x01\x00" * 8000

    import services.tts.qwen_gguf as qg

    monkeypatch.setattr(qg, "synthesize_stream", fake_stream)

    def run(text):
        out_q: queue.Queue = queue.Queue()
        req = worker.SynthesizeRequest(
            call_id="t", generation_id="g", phrase_id="p", text=text
        )
        n = worker._produce_qwen_chunks(req, out_q, {})
        items = []
        while True:
            try:
                items.append(out_q.get_nowait())
            except queue.Empty:
                break
        return n, items

    n1, items1 = run("Здравствуйте.")
    n2, items2 = run("Здравствуйте.")
    assert n1 > 0 and n2 == n1
    assert [i["pcm_b64"] for i in items1] == [i["pcm_b64"] for i in items2]
    assert calls == ["Здравствуйте."], calls
    worker._QWEN_PHRASE_CACHE.clear()


def test_qwen_phrase_cache_capped() -> None:
    import services.tts.worker as worker

    worker._QWEN_PHRASE_CACHE.clear()
    for i in range(worker._QWEN_PHRASE_CACHE_MAX + 5):
        worker._QWEN_PHRASE_CACHE[("v", "Russian", f"t{i}")] = [(b"x", 24000)]
        while len(worker._QWEN_PHRASE_CACHE) > worker._QWEN_PHRASE_CACHE_MAX:
            worker._QWEN_PHRASE_CACHE.pop(next(iter(worker._QWEN_PHRASE_CACHE)))
    assert len(worker._QWEN_PHRASE_CACHE) == worker._QWEN_PHRASE_CACHE_MAX
    worker._QWEN_PHRASE_CACHE.clear()
