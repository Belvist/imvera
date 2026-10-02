"""Startup preserves the selected voice provider and checks the real call path."""

from __future__ import annotations

import base64
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from scripts import (
    dialogue_product_smoke,
    freeswitch_voice_lab_env,
    freeswitch_zoiper_voice_up,
    models_up,
    prerender_opening,
)
from services.tts import worker


def _ready(revision: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"model_revision": revision},
        request=httpx.Request("GET", "http://127.0.0.1:9102/health/ready"),
    )


@pytest.mark.parametrize("lab_fast", ["0", "1"])
def test_selected_mlx_timeout_never_starts_silero(monkeypatch, lab_fast) -> None:
    launched = []
    monkeypatch.setattr(models_up, "is_running", lambda _: False)
    monkeypatch.setattr(models_up, "stop", lambda _: None)
    monkeypatch.setattr(models_up, "_wait_ready", lambda *_, **__: False)
    monkeypatch.setattr(
        models_up, "start", lambda name, args, *, env: launched.append((name, env.copy()))
    )
    env = {"IMVERA_TTS_ENGINE": "mlx_customvoice", "IMVERA_LAB_FAST_TTS": lab_fast}
    assert models_up._ensure_worker("tts", 9102, env) is False
    assert len(launched) == 1
    assert launched[0][1]["IMVERA_TTS_ENGINE"] == "mlx_customvoice"
    assert launched[0][1]["IMVERA_LAB_FAST_TTS"] == lab_fast


@pytest.mark.parametrize("load_timeout", [120.0, 420.0])
def test_mlx_startup_allows_loading_then_warmup(monkeypatch, load_timeout) -> None:
    monkeypatch.setattr(models_up, "is_running", lambda _: False)
    monkeypatch.setattr(models_up, "stop", lambda _: None)
    monkeypatch.setattr(models_up, "start", lambda *_, **__: None)
    monkeypatch.setattr(models_up.httpx, "get", lambda *_, **__: _ready(
        "mlx_customvoice:chosen-model"
    ))
    waited = []

    def wait(*_, timeout_s):
        waited.append(timeout_s)
        return True

    monkeypatch.setattr(models_up, "_wait_ready", wait)
    env = {
        "IMVERA_TTS_ENGINE": "mlx_customvoice",
        "IMVERA_TTS_MLX_LOAD_TIMEOUT_S": str(load_timeout),
    }
    assert models_up._ensure_worker("tts", 9102, env) is True
    assert waited[0] >= load_timeout + 180.0
    assert waited[0] <= load_timeout + 200.0


@pytest.mark.parametrize("revision, should_restart", [
    ("mlx_customvoice:chosen-model", False),
    ("silero_lab:silero:v5_ru:kseniya", True),
])
def test_zoiper_shortcut_keeps_only_selected_provider(
    monkeypatch, revision, should_restart
) -> None:
    monkeypatch.setenv("IMVERA_TTS_ENGINE", "mlx_customvoice")
    monkeypatch.setenv("IMVERA_LAB_FAST_TTS", "0")
    monkeypatch.setattr(freeswitch_zoiper_voice_up, "is_running", lambda _: True)
    monkeypatch.setattr(freeswitch_zoiper_voice_up.httpx, "get", lambda *_, **__: _ready(revision))
    starts = []

    def run(args, **kwargs):
        starts.append((args, kwargs["env"]))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    assert freeswitch_zoiper_voice_up._ensure_mlx_workers() == 0
    assert bool(starts) is should_restart
    if should_restart:
        assert starts[0][0][-1].endswith("scripts/models_up.py")
        assert starts[0][1]["IMVERA_MODELS_WORKERS"] == "stt,tts"
        assert starts[0][1]["IMVERA_TTS_ENGINE"] == "mlx_customvoice"


@pytest.mark.parametrize("lab_fast", ["0", "1"])
@pytest.mark.parametrize("failure", ["load", "warmup"])
def test_selected_mlx_worker_failure_stays_not_ready(monkeypatch, lab_fast, failure) -> None:
    monkeypatch.setenv("IMVERA_TTS_ENGINE", "mlx_customvoice")
    monkeypatch.setenv("IMVERA_LAB_FAST_TTS", lab_fast)
    monkeypatch.setenv("IMVERA_SILERO_LAB_ACK", "1")
    monkeypatch.setattr(worker.state, "ready", False)
    monkeypatch.setattr(worker.state, "warmup_error", None)
    monkeypatch.setattr(worker, "_tts", None)
    monkeypatch.setattr(
        worker, "_load_mlx_model",
        lambda *_: (None, "load timeout") if failure == "load" else (object(), None),
    )
    monkeypatch.setattr("services.tts.warmup.warmup_synthesis", lambda *_, **__: 0.0)
    initialized = []
    monkeypatch.setattr(worker, "_init_silero_lab", lambda _: initialized.append(True) or True)
    worker._load_and_warmup_mlx({"id": "chosen-model"}, "mlx_customvoice")
    assert initialized == []
    assert worker.state.ready is False
    assert worker.state.warmup_error
    assert worker.tts_engine({}) == "mlx_customvoice"


@pytest.mark.parametrize("lab_fast", ["0", "1"])
@pytest.mark.parametrize("revision, matches", [
    ("mlx_customvoice:chosen-model", True),
    ("silero_lab:silero:v5_ru:kseniya", False),
])
def test_readiness_matches_explicit_mlx_selection(monkeypatch, lab_fast, revision, matches) -> None:
    monkeypatch.setenv("IMVERA_TTS_ENGINE", "mlx_customvoice")
    monkeypatch.setenv("IMVERA_LAB_FAST_TTS", lab_fast)
    monkeypatch.setattr(models_up.httpx, "get", lambda *_, **__: _ready(revision))
    assert models_up._tts_matches_lab_fast(9102) is matches


def test_opening_accepts_selected_live_mlx_without_prerender(monkeypatch) -> None:
    env = {
        "IMVERA_TTS_ENGINE": "mlx_customvoice",
        "IMVERA_LAB_FAST_TTS": "0",
        "IMVERA_OPENING_CACHE": "0",
    }
    monkeypatch.setattr(freeswitch_voice_lab_env.httpx, "get", lambda *_, **__: _ready(
        "mlx_customvoice:chosen-model"
    ))
    renders = []
    monkeypatch.setattr(subprocess, "run", lambda *_, **__: renders.append(True))
    assert freeswitch_voice_lab_env.ensure_silero_opening_cache(env) is True
    assert env["IMVERA_TTS_MODEL_REVISION"] == "mlx_customvoice:chosen-model"
    assert renders == []


def test_opening_rejects_provider_mismatch(monkeypatch) -> None:
    env = {"IMVERA_TTS_ENGINE": "mlx_customvoice", "IMVERA_OPENING_CACHE": "0"}
    monkeypatch.setattr(freeswitch_voice_lab_env.httpx, "get", lambda *_, **__: _ready(
        "silero_lab:silero:v5_ru:kseniya"
    ))
    assert freeswitch_voice_lab_env.ensure_silero_opening_cache(env) is False


def test_default_lab_still_prerenders_selected_silero(monkeypatch, tmp_path) -> None:
    env = {"IMVERA_TTS_ENGINE": "silero_lab", "IMVERA_OPENING_CACHE": "1"}
    monkeypatch.setattr(freeswitch_voice_lab_env, "ROOT", tmp_path)
    monkeypatch.setattr(freeswitch_voice_lab_env.httpx, "get", lambda *_, **__: _ready(
        "silero_lab:silero:v5_ru:kseniya"
    ))
    rendered = []
    def run(*_, **kwargs):
        rendered.append(kwargs["env"])
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr(subprocess, "run", run)
    assert freeswitch_voice_lab_env.ensure_silero_opening_cache(env) is True
    assert rendered == [env]


def test_product_smoke_checks_callactor_without_gateway_or_llm(monkeypatch, capsys) -> None:
    monkeypatch.setenv("IMVERA_MEDIA_BRIDGE_HTTP", "http://bridge:9210")
    monkeypatch.setenv("IMVERA_STT_URL", "http://stt:9101")
    monkeypatch.setenv("IMVERA_TTS_URL", "http://tts:9102")
    contacted = []

    def get(url, **_):
        contacted.append(url)
        assert url in {
            "http://bridge:9210/health/ready",
            "http://stt:9101/health/ready",
            "http://tts:9102/health/ready",
        }
        payload = {"status": "ok"}
        if "bridge" in url:
            payload.update({
                "mode": "callactor",
                "stt": "http://stt:9101",
                "tts": "http://tts:9102",
                "dialogue": {
                    "dialogue.engine.enabled": True, "dialogue.engine.mode": "single_writer",
                },
            })
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(dialogue_product_smoke.httpx, "get", get)
    gates = []
    monkeypatch.setattr(subprocess, "check_call", lambda args, **_: gates.append(args))
    assert dialogue_product_smoke.main() == 0
    assert len(contacted) == 3
    assert gates == [["make", "test-dialogue-gates"]]
    assert "NOT VERIFIED" in capsys.readouterr().out


def test_product_smoke_checks_each_active_replica(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_MEDIA_BRIDGE_HTTP", "http://bridge:9210")
    monkeypatch.setenv("IMVERA_STT_URL", " http://stt:9101/,http://stt2:9101 ")
    monkeypatch.setenv("IMVERA_TTS_URL", "http://tts:9102/,http://tts2:9102")
    contacted = []

    def get(url, **_):
        contacted.append(url)
        payload = {"status": "ok"}
        if "bridge" in url:
            payload.update({
                "mode": "callactor",
                "stt": "http://stt:9101,http://stt2:9101",
                "tts": "http://tts:9102,http://tts2:9102",
                "dialogue": {
                    "dialogue.engine.enabled": True, "dialogue.engine.mode": "single_writer",
                },
            })
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(dialogue_product_smoke.httpx, "get", get)
    monkeypatch.setattr(subprocess, "check_call", lambda *_, **__: 0)
    assert dialogue_product_smoke.main() == 0
    assert contacted == [
        "http://bridge:9210/health/ready",
        "http://stt:9101/health/ready",
        "http://stt2:9101/health/ready",
        "http://tts:9102/health/ready",
        "http://tts2:9102/health/ready",
    ]


def test_product_smoke_blocks_foreign_provider_before_probing_it(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_MEDIA_BRIDGE_HTTP", "http://bridge:9210")
    monkeypatch.setenv("IMVERA_STT_URL", "http://foreign-stt:9101")
    contacted = []

    def get(url, **_):
        contacted.append(url)
        return httpx.Response(200, json={
            "mode": "callactor",
            "stt": "http://active-stt:9101",
            "tts": "http://tts:9102",
            "dialogue": {
                "dialogue.engine.enabled": True, "dialogue.engine.mode": "single_writer",
            },
        }, request=httpx.Request("GET", url))

    monkeypatch.setattr(dialogue_product_smoke.httpx, "get", get)
    monkeypatch.setattr(
        subprocess, "check_call", lambda *_, **__: pytest.fail("must fail before gates")
    )
    with pytest.raises(SystemExit):
        dialogue_product_smoke.main()
    assert contacted == ["http://bridge:9210/health/ready"]


@pytest.mark.parametrize("payload", [
    {"status": "ok", "mode": "echo"},
    {"status": "ok", "mode": "callactor", "dialogue": {"dialogue.engine.enabled": False}},
])
def test_product_smoke_blocks_wrong_dialogue_path(monkeypatch, payload) -> None:
    monkeypatch.setattr(dialogue_product_smoke.httpx, "get", lambda url, **_: httpx.Response(
        200, json=payload, request=httpx.Request("GET", url)
    ))
    monkeypatch.setattr(
        subprocess, "check_call", lambda *_, **__: pytest.fail("must fail before gates")
    )
    with pytest.raises(SystemExit):
        dialogue_product_smoke.main()


def test_prerender_uses_selected_mlx_pcm_and_revision(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_TTS_ENGINE", "mlx_customvoice")
    monkeypatch.setattr(prerender_opening.httpx, "get", lambda *_, **__: _ready(
        "mlx_customvoice:chosen-model"
    ))
    monkeypatch.setattr(prerender_opening, "_opening_text", lambda _: "Здравствуйте.")
    pcm = b"\x01\x00" * 160
    calls = []
    saved = []

    class Stream:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield json.dumps({
                "pcm_b64": base64.b64encode(pcm).decode(), "sample_rate": 24000,
            })
            yield json.dumps({"done": True})

    class Client:
        def __init__(self, **_):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        @contextmanager
        def stream(self, *args, **kwargs):
            calls.append((args, kwargs))
            yield Stream()

    monkeypatch.setattr(prerender_opening.httpx, "Client", Client)

    def save(text, audio, sample_rate, *, engine):
        saved.append((text, audio, sample_rate, engine))
        return Path("opening_test.json")

    monkeypatch.setattr(prerender_opening, "save_opening", save)
    assert prerender_opening.main() == 0
    assert saved == [("Здравствуйте.", pcm, 24000, "mlx_customvoice:chosen-model")]
    assert calls[0][1]["json"]["text"] == "Здравствуйте."
