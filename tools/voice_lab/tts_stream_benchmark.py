"""Measure real HTTP/provider first PCM and completion, never audible latency."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from services.tts.http_provider import HttpTTSProvider


def percentile(values: list[float], percent: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percent / 100) - 1)]


async def benchmark(args: argparse.Namespace) -> dict:
    async with httpx.AsyncClient(timeout=args.timeout_s) as client:
        ready_response = await client.get(f"{args.url.rstrip('/')}/health/ready")
        ready_response.raise_for_status()
        readiness = ready_response.json()
        provider = HttpTTSProvider(args.url, client=client)
        admission = asyncio.Semaphore(args.concurrency)

        async def measure(index: int) -> dict:
            async with admission:
                start = time.monotonic()
                first = None
                chunks = 0
                audio_s = 0.0
                generation_id = f"bench-{time.time_ns()}-{index}"
                error = None
                try:
                    async for chunk in provider.synthesize(
                        args.text,
                        call_id="tts-stream-benchmark",
                        generation_id=generation_id,
                        phrase_id="benchmark",
                        deadline=start + args.timeout_s,
                    ):
                        if not chunk.pcm_s16le:
                            continue
                        if first is None:
                            first = (time.monotonic() - start) * 1000
                        chunks += 1
                        audio_s += len(chunk.pcm_s16le) / (2 * chunk.sample_rate)
                    if first is None:
                        error = "no_pcm"
                except Exception as exc:
                    error = type(exc).__name__
                if error is not None:
                    await provider.cancel(generation_id)
                return {
                    "index": index,
                    "first_pcm_ms": first,
                    "completion_ms": (time.monotonic() - start) * 1000,
                    "pcm_chunks": chunks,
                    "audio_s": audio_s,
                    "error": error,
                }

        warmup = await measure(-1)
        if warmup["error"]:
            raise RuntimeError(f"benchmark warmup failed: {warmup['error']}")
        samples = await asyncio.gather(*(measure(index) for index in range(args.runs)))
    valid = [sample for sample in samples if sample["error"] is None]
    first = [sample["first_pcm_ms"] for sample in valid]
    complete = [sample["completion_ms"] for sample in valid]
    return {
        "boundary": "HTTP request→first PCM; not speech-end, SIP or audible sound",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "tool_git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
        ).strip(),
        "endpoint": args.url,
        "label": args.label,
        "text": args.text,
        "concurrency": args.concurrency,
        "worker_readiness": readiness,
        "worker_git_sha": "NOT_VERIFIED: readiness does not expose deployed SHA",
        "warmup_excluded": warmup,
        "runs": args.runs,
        "errors": len(samples) - len(valid),
        "first_pcm_p50_ms": percentile(first, 50),
        "first_pcm_p95_ms": percentile(first, 95),
        "completion_p50_ms": percentile(complete, 50),
        "completion_p95_ms": percentile(complete, 95),
        "samples": samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--text", default="Поняла, сегодня было непросто. Расскажите, что вас беспокоит?"
    )
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout-s", type=float, default=20)
    parser.add_argument("--label", required=True, help="Record active worker flags/hardware here")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        parser.error("--url must be an HTTP(S) worker endpoint without embedded credentials")
    if args.runs <= 0 or args.concurrency <= 0 or args.timeout_s <= 0:
        parser.error("runs, concurrency and timeout must be positive")
    result = asyncio.run(benchmark(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "samples"},
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(1 if result["errors"] else 0)


if __name__ == "__main__":
    main()
