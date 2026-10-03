"""Real GigaAM in an explicitly named local Docker worker; repository WAVs only."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import subprocess
import time
import wave
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    env = dict(os.environ)
    for key in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ):
        env.pop(key, None)
    prefix = ["docker", "--host=unix:///var/run/docker.sock"]

    def docker(*command):
        return subprocess.check_output(prefix + list(command), env=env, text=True)

    info = json.loads(docker("inspect", args.container))[0]
    port = info["NetworkSettings"]["Ports"]["9101/tcp"][0]
    assert port["HostIp"] == "127.0.0.1", "probe only the explicitly local worker"
    url = "http://127.0.0.1:" + port["HostPort"]
    source_sha = info["Config"]["Labels"]["org.opencontainers.image.revision"]
    record = {
        "source_sha": source_sha,
        "image_id": info["Image"],
        "boundary": "real GigaAM + Linux HTTP worker; repository WAVs, no SIP/TTS",
        "cases": [],
    }
    end = time.monotonic() + 240
    with httpx.Client(timeout=15) as client:
        while time.monotonic() < end:
            try:
                response = client.get(url + "/health/ready")
                if response.status_code == 200:
                    record["ready"] = response.json()
                    break
            except httpx.HTTPError:
                pass
            assert (
                docker("inspect", "--format", "{{.State.Running}}", args.container).strip()
                == "true"
            )
            time.sleep(0.2)
        else:
            raise TimeoutError("real model warmup timeout")
        assert record["ready"]["runtime"]["git_sha"] == source_sha
        for index, sample in enumerate(
            ("wellness_bad_03", "decline_nothing_hurts_01", "mood_positive_01", "plans_walk_01")
        ):
            path = Path("tests/assets/blackbox_voice/wav") / (sample + ".wav")
            with wave.open(str(path), "rb") as audio:
                assert audio.getnchannels() == 1 and audio.getsampwidth() == 2
                rate = audio.getframerate()
                pcm = audio.readframes(audio.getnframes())
            payload = {
                "request_id": f"linux-wav-{index}",
                "call_id": "repository-wav-proof",
                "turn_id": index,
                "sample_rate": rate,
                "pcm_b64": base64.b64encode(pcm).decode(),
                "timeout_s": 12,
            }
            started = time.monotonic()
            response = client.post(url + "/v1/transcribe", json=payload)
            elapsed = (time.monotonic() - started) * 1000
            response.raise_for_status()
            result = response.json()
            assert result["is_final"] and isinstance(result["text"], str) and result["text"].strip()
            record["cases"].append(
                {
                    "fixture": str(path),
                    "audio_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "http_latency_ms": elapsed,
                    "response": result,
                }
            )
        times = sorted(case["http_latency_ms"] for case in record["cases"])
        record["samples"] = len(times)
        record["http_p50_ms"] = (times[1] + times[2]) / 2
        record["http_p95_nearest_rank_ms"] = times[math.ceil(0.95 * len(times)) - 1]
        record["after"] = client.get(url + "/health/ready").json()
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
