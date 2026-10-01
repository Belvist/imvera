"""Probe boundaries and actual HTTP request shape; no model-quality claims."""

import asyncio
import json
import wave

import httpx
import pytest

from services.stt.http_provider import HttpSTTProvider
from tools.voice_lab.stt_preview_probe import load_pcm, measure, summary


@pytest.mark.parametrize("channels,width,rate,seconds", [
    (2, 2, 16000, 1), (1, 1, 16000, 1), (1, 2, 48000, 1),
    (1, 2, 16000, 0.5), (1, 2, 16000, 21),
], ids=["stereo", "pcm8", "wrong_rate", "too_short", "too_long"])
def test_probe_rejects_audio_outside_real_runtime_contract(
    tmp_path, channels, width, rate, seconds,
):
    path = tmp_path / "audio.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(bytes(int(seconds * rate * channels * width)))
    with pytest.raises(ValueError):
        load_pcm(path)


def test_paired_probe_submits_identical_final_pcm_and_keeps_previews_nonfinal():
    async def scenario():
        requests = []

        def respond(req):
            body = json.loads(req.content)
            requests.append((req.url.path, body))
            if req.url.path == "/v1/preview":
                return httpx.Response(200, json={
                    "request_id": body["request_id"], "partial_id": body["partial_id"],
                    "text": "болит", "is_final": False, "partial_mode": "prefix_batch",
                    "model_revision": "boundary-fixture",
                })
            assert req.url.path == "/v1/transcribe", "probe may only invoke STT"
            return httpx.Response(200, json={"request_id": body["request_id"],
                                             "text": "не болит", "is_final": True,
                                             "model_revision": "boundary-fixture"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            provider = HttpSTTProvider("http://stt", client=client, prefix_previews=True)
            pcm = b"\x10\x10" * 17600  # 1.1s source, 1s preview before final
            baseline = await measure(provider, pcm, 16000, prefix_previews=False, run_id="off")
            preview = await measure(provider, pcm, 16000, prefix_previews=True, run_id="on")
        assert len(requests) == 3
        finals = [body for path, body in requests if path == "/v1/transcribe"]
        assert len(finals) == 2 and finals[0]["pcm_b64"] == finals[1]["pcm_b64"]
        assert baseline["previews"] == []
        assert len(preview["previews"]) == 1 and not preview["previews"][0]["is_final"]
        assert baseline["final_transcript_sha256"] == preview["final_transcript_sha256"]
        assert baseline["final_submission_boundary"] == preview["final_submission_boundary"]
        assert summary([baseline, preview], True)["percentile_use"] == "diagnostic_only"

    asyncio.run(scenario())
