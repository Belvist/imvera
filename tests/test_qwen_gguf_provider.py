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


def test_voice_default_serena() -> None:
    assert qwen_gguf.qwen_voice({}) == "serena"


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
