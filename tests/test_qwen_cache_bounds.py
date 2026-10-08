"""Exercise real Qwen producer caching, with a controlled PCM upstream.

No resident speech model is replaced in production; tests prove byte delivery,
identity isolation, memory retention and cancellation/deadline behavior only.
"""
from __future__ import annotations

import base64
import queue
import time
from collections import OrderedDict

import pytest

from services.tts import qwen_gguf, worker


@pytest.fixture
def cache(monkeypatch):
    monkeypatch.setattr(worker, "_QWEN_PHRASE_CACHE", OrderedDict())
    monkeypatch.setattr(worker, "_QWEN_CACHE_BYPASS", False)
    monkeypatch.setattr(worker, "_is_cancelled", lambda req: False)
    monkeypatch.setattr(worker.state, "model_revision", "qwen_gguf:model-A")
    monkeypatch.delenv("IMVERA_QWEN_TTS_VOICE", raising=False)
    monkeypatch.setenv("IMVERA_QWEN_TTS_URL", "http://resident-a:8899")
    calls = []

    def stream(text, **kwargs):
        calls.append((text, kwargs))
        yield b"\x01\x00" * 4

    monkeypatch.setattr(qwen_gguf, "synthesize_stream", stream)
    return calls


def render(text="Здравствуйте.", cfg=None, **kwargs):
    req = worker.SynthesizeRequest(call_id="cache-test", generation_id="g",
                                   phrase_id="p", text=text, **kwargs)
    out = queue.Queue()
    count = worker._produce_qwen_chunks(req, out, cfg or {})
    frames = list(out.queue)
    assert count == len(frames)
    return b"".join(base64.b64decode(frame["pcm_b64"]) for frame in frames)


def retained_bytes():
    return sum(len(pcm) for chunks in worker._QWEN_PHRASE_CACHE.values() for pcm, _ in chunks)


def test_cache_hit_keeps_exact_pcm_without_new_inference(cache):
    assert render() == render() == b"\x01\x00" * 4
    assert len(cache) == 1


@pytest.mark.parametrize("change", ["model", "endpoint", "config_voice", "environment_voice"])
def test_cache_identity_isolates_backend_and_effective_voice(cache, monkeypatch, change):
    render()
    cfg = {}
    if change == "model":
        monkeypatch.setattr(worker.state, "model_revision", "qwen_gguf:model-B")
    elif change == "endpoint":
        monkeypatch.setenv("IMVERA_QWEN_TTS_URL", "http://resident-b:8899")
    elif change == "config_voice":
        cfg = {"qwen_gguf": {"voice": "other-voice"}}
    else:
        monkeypatch.setenv("IMVERA_QWEN_TTS_VOICE", "other-voice")
    render(cfg=cfg)
    assert len(cache) == 2


def test_true_lru_keeps_the_recently_used_phrase(cache, monkeypatch):
    monkeypatch.setattr(worker, "_QWEN_PHRASE_CACHE_MAX", 2)
    for text in ["A", "B", "A", "C", "A", "B"]:
        render(text)
    assert [text for text, _ in cache] == ["A", "B", "C", "B"]


def test_retained_pcm_has_a_byte_limit(cache, monkeypatch):
    monkeypatch.setattr(worker, "_QWEN_PHRASE_CACHE_MAX_BYTES", 12, raising=False)
    render("A")
    render("B")
    assert retained_bytes() <= 12
    render("A")
    assert len(cache) == 3


def test_oversized_render_is_delivered_but_never_retained(cache, monkeypatch):
    monkeypatch.setattr(worker, "_QWEN_PHRASE_CACHE_MAX_BYTES", 12, raising=False)

    def stream(text, **kwargs):
        cache.append((text, kwargs))
        yield b"\x01\x00" * 4
        yield b"\x02\x00" * 4

    monkeypatch.setattr(qwen_gguf, "synthesize_stream", stream)
    assert render() == render() == b"\x01\x00" * 4 + b"\x02\x00" * 4
    assert retained_bytes() == 0
    assert len(cache) == 2


def test_expired_cache_hit_sends_no_audio(cache):
    render()
    out = queue.Queue()
    req = worker.SynthesizeRequest(call_id="cache-test", generation_id="g", phrase_id="p",
                                   text="Здравствуйте.", deadline=time.monotonic() - 1)
    with pytest.raises(TimeoutError):
        worker._produce_qwen_chunks(req, out, {})
    assert out.empty()
    assert len(cache) == 1


def test_cancellation_inside_one_upstream_pcm_stops_next_frame(cache, monkeypatch):
    cancelled = False

    class CancellingQueue(queue.Queue):
        def put(self, item, *args, **kwargs):
            nonlocal cancelled
            super().put(item, *args, **kwargs)
            cancelled = True

    monkeypatch.setattr(worker, "_is_cancelled", lambda req: cancelled)
    monkeypatch.setattr(qwen_gguf, "synthesize_stream", lambda *a, **k: iter([b"\x01\x00" * 10000]))
    out = CancellingQueue()
    req = worker.SynthesizeRequest(call_id="cache-test", generation_id="g", phrase_id="p", text="A")
    assert worker._produce_qwen_chunks(req, out, {}) == 1
    assert retained_bytes() == 0


def test_bypass_does_not_read_or_store_cache(cache):
    render()
    with worker.qwen_cache_bypassed():
        render()
    render()
    assert len(cache) == 2


def test_cached_stream_rechecks_deadline_before_each_pcm_frame(cache, monkeypatch):
    monkeypatch.setattr(qwen_gguf, "synthesize_stream",
                        lambda *a, **k: iter([b"\x01\x00" * 10000]))
    render()
    checked = 0

    def deadline(_):
        nonlocal checked
        checked += 1
        if checked >= 3:
            raise TimeoutError("deadline after first PCM")

    monkeypatch.setattr(worker, "check_deadline", deadline)
    out = queue.Queue()
    req = worker.SynthesizeRequest(call_id="cache-test", generation_id="g",
                                   phrase_id="p", text="Здравствуйте.")
    with pytest.raises(TimeoutError):
        worker._produce_qwen_chunks(req, out, {})
    assert out.qsize() == 1


def test_failure_after_pcm_is_never_cached(cache, monkeypatch):
    def stream(*args, **kwargs):
        yield b"\x01\x00" * 4
        raise RuntimeError("upstream failed")

    monkeypatch.setattr(qwen_gguf, "synthesize_stream", stream)
    with pytest.raises(worker._QwenStreamFailure) as failure:
        render()
    assert failure.value.emitted_chunks == 1
    assert retained_bytes() == 0


def test_explicit_voice_overrides_environment_and_config(cache, monkeypatch):
    monkeypatch.setenv("IMVERA_QWEN_TTS_VOICE", "env-voice")
    render(cfg={"qwen_gguf": {"voice": "cfg-voice"}}, voice="chosen-voice")
    assert cache[0][1]["voice"] == "chosen-voice"
    monkeypatch.setenv("IMVERA_QWEN_TTS_VOICE", "other-env")
    render(cfg={"qwen_gguf": {"voice": "other-cfg"}}, voice="chosen-voice")
    assert len(cache) == 1
