#!/usr/bin/env python3
"""Paired same-WAV prefix-batch load probe against an explicit existing STT URL.

Replay boundary is source WAV end, not acoustic endpoint or telephone latency.
No models are downloaded, no TTS/Core/dialogue actions are invoked.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import time
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import httpx

from packages.contracts.stt import STT_PREVIEW_CHECKPOINTS_MS
from services.stt.http_provider import HttpSTTProvider


def load_pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
            raise ValueError("requires uncompressed mono PCM16 WAV")
        if wav.getframerate() != 16000:
            raise ValueError("requires 16kHz WAV, matching the current runtime STT branch")
        pcm = wav.readframes(wav.getnframes())
    if not 32000 <= len(pcm) <= 20 * 32000:
        raise ValueError("requires 1–20 seconds of audio (current utterance limit)")
    return pcm, 16000


async def measure(
    provider: HttpSTTProvider, pcm: bytes, sample_rate: int, *,
    prefix_previews: bool, run_id: str,
) -> dict:
    duration_s = len(pcm) / (sample_rate * 2)
    started = time.monotonic()
    task: asyncio.Task | None = None
    tasks = []
    observations = []

    async def preview(checkpoint: int) -> None:
        requested = time.monotonic()
        observation = {"checkpoint_ms": checkpoint, "status": "requested"}
        observations.append(observation)
        try:
            result = await provider.transcribe_partial(
                pcm[:sample_rate * 2 * checkpoint // 1000], sample_rate,
                call_id=run_id, partial_id=f"{run_id}:p{checkpoint}",
            )
            observation.update(status="observed", is_final=result.is_final,
                               model_revision=result.model_revision,
                               transcript_sha256=hashlib.sha256(result.text.encode()).hexdigest())
        except asyncio.CancelledError:
            observation["status"] = "cancelled_at_source_end"
            raise
        except Exception as exc:
            observation.update(status="unavailable", error=str(exc)[:200])
        finally:
            observation["request_ms"] = round((time.monotonic() - requested) * 1000, 2)

    try:
        if prefix_previews:
            for checkpoint in STT_PREVIEW_CHECKPOINTS_MS:
                if checkpoint / 1000 >= duration_s:
                    break
                await asyncio.sleep(max(0, started + checkpoint / 1000 - time.monotonic()))
                if task is not None and not task.done():
                    observations.append({"checkpoint_ms": checkpoint, "status": "skipped_inflight"})
                    continue
                task = asyncio.create_task(preview(checkpoint))
                tasks.append(task)
        await asyncio.sleep(max(0, started + duration_s - time.monotonic()))
        for pending in tasks:
            if not pending.done():
                pending.cancel()
        final_requested = time.monotonic()
        result = await provider.transcribe_final(
            pcm, sample_rate, call_id=run_id, turn_id=1,
            utterance_id="u-1", deadline=final_requested + 12.0,
        )
        return {
            "prefix_previews": prefix_previews,
            "audio_duration_ms": round(duration_s * 1000),
            "final_request_ms": round((time.monotonic() - final_requested) * 1000, 2),
            "source_end_to_final_ms": round((time.monotonic() - started - duration_s) * 1000, 2),
            "final_submission_boundary": "source_wav_end",
            "model_revision": result.model_revision,
            "asr_quality": str(result.asr_quality),
            "final_transcript_sha256": hashlib.sha256(result.text.encode()).hexdigest(),
            "previews": observations,
        }
    finally:
        for pending in tasks:
            if not pending.done():
                pending.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def summary(rows: list[dict], enabled: bool) -> dict:
    values = sorted(row["final_request_ms"] for row in rows
                    if row["prefix_previews"] == enabled)
    return {
        "samples": len(values),
        "final_request_p50_ms": round(statistics.median(values), 2),
        "final_request_p95_ms": values[max(0, math.ceil(len(values) * 0.95) - 1)],
        "percentile_use": "diagnostic_only" if len(values) < 20 else "paired_STT_probe_only",
    }


async def run(args: argparse.Namespace) -> dict:
    if "," in args.stt_url:
        raise ValueError("paired probe requires one worker URL, not a replica pool")
    pcm, rate = load_pcm(args.wav)
    rows = []
    async with httpx.AsyncClient() as client:
        provider = HttpSTTProvider(args.stt_url, client=client, prefix_previews=True)
        capabilities = await provider.capabilities()
        if (capabilities.partial_mode != "prefix_batch" or capabilities.native_streaming
                or not capabilities.final_required):
            raise ValueError("worker must explicitly advertise prefix_batch/final_required")
        for number in range(args.runs):
            # Alternate order to reduce systematic warmup/order bias.
            for enabled in ((False, True) if number % 2 == 0 else (True, False)):
                rows.append(await measure(provider, pcm, rate, prefix_previews=enabled,
                                          run_id=f"probe-{time.time_ns()}"))
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO).strip())
    return {
        "git_sha": sha, "dirty": dirty, "client_platform": platform.platform(),
        "worker_hardware_note": args.worker_hardware,
        "worker_code_revision_note": args.worker_revision,
        "input_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "sample_rate": rate, "capabilities": capabilities.model_dump(),
        "native_streaming": False, "phone_latency_evaluated": False,
        "listener_warmth_evaluated": False,
        "source_hashes": {
            name: hashlib.sha256((REPO / name).read_bytes()).hexdigest()
            for name in ("services/stt/http_provider.py", "services/stt/worker.py",
                         "services/inference/common.py",
                         "tools/voice_lab/stt_preview_probe.py")
        },
        "final_only": summary(rows, False), "with_previews": summary(rows, True),
        "runs": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--stt-url", required=True, help="Explicit lab worker URL")
    parser.add_argument("--worker-hardware", required=True, help="Actual server CPU/GPU/RAM")
    parser.add_argument("--worker-revision", required=True,
                        help="Verified active server Git/image SHA")
    parser.add_argument("--runs", type=int, default=3, help="Paired samples, not full calls")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    report = asyncio.run(run(args))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "final_only": report["final_only"],
                      "with_previews": report["with_previews"],
                      "phone_latency_evaluated": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
