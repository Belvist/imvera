"""Capacity probe: N parallel synthetic calls, honest ceiling measurement.

Usage:
    python3 scripts/capacity_probe.py --levels 1 2 4 8 --turns 4

Each synthetic call runs `turns` full turns against the LIVE local stack:
STT transcribe (real worker) -> CallSession.handle_user_text (real engine)
-> TTS synthesize (real worker). Grandmother's real voice segment is the
STT input. Reports per-level p50/p95 turn latency + error/503 counts +
trace drops. No assertions about "production" — just the measured curve.

Run with PILOT traces (IMVERA_OBS_MODE=pilot) to measure the load tiers.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from services.stt.http_provider import HttpSTTProvider
from services.tts.http_provider import HttpTTSProvider

TURNS = ["хорошо", "поела недавно", "да, приняла", "всё хорошо"]


def _load_grandma_pcm() -> bytes:
    for cand in sorted((_ROOT / ".run" / "vera_demo").glob("*_s1.wav")):
        raw = cand.read_bytes()
        if len(raw) > 1000:
            return raw[44:]
    raise FileNotFoundError("no grandma segment wav in .run/vera_demo")


def _pct(samples: list[float], pct: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(len(ordered) * pct / 100))]


def _one_call(
    call_idx: int, turns: int, pcm_b64: str, urls: dict[str, str]
) -> dict:
    async def _run() -> dict:
        stt = HttpSTTProvider(urls["stt"])
        tts = HttpTTSProvider(urls["tts"])
        session = CallSession(
            call_id=f"probe-{call_idx}-{int(time.time())}",
            family_id="probe",
            store=InMemoryCallRecordStore(),
        )
        session.start()
        session.state.mandatory_checks.update(
            identity=True, consent=True, can_talk=True
        )
        session.state.greeted = True
        lat: list[float] = []
        errors = 0
        pcm_raw = base64.b64decode(pcm_b64)
        for i in range(turns):
            t0 = time.perf_counter()
            try:
                deadline = time.monotonic() + 60
                await stt.transcribe_final(
                    pcm_raw,
                    16000,
                    call_id="probe",
                    turn_id=i,
                    deadline=deadline,
                    utterance_id=f"u{i}",
                )
                session.handle_user_text(TURNS[i % len(TURNS)])
                pcm_out = b""
                async for ch in tts.synthesize(
                    "Поняла вас.",
                    call_id="probe",
                    generation_id=f"g{call_idx}-{i}",
                    phrase_id="p",
                    deadline=time.monotonic() + 60,
                ):
                    pcm_out += ch.pcm_s16le
                if not pcm_out:
                    errors += 1
                lat.append((time.perf_counter() - t0) * 1000)
            except Exception:
                errors += 1
        return {"lat": lat, "errors": errors}

    return asyncio.run(_run())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8])
    ap.add_argument("--turns", type=int, default=4)
    ap.add_argument("--stt", default="http://127.0.0.1:9101,http://127.0.0.1:9111")
    ap.add_argument("--tts", default="http://127.0.0.1:9102,http://127.0.0.1:9112")
    args = ap.parse_args()

    pcm_b64 = base64.b64encode(_load_grandma_pcm()).decode()
    urls = {"stt": args.stt, "tts": args.tts}
    report = {"levels": {}, "obs_mode": os.environ.get("IMVERA_OBS_MODE", "debug")}
    for level in args.levels:
        with ThreadPoolExecutor(max_workers=level) as pool:
            futs = [
                pool.submit(_one_call, ci, args.turns, pcm_b64, urls)
                for ci in range(level)
            ]
            results = [f.result() for f in futs]
        lat = [x for r in results for x in r["lat"]]
        err = sum(r["errors"] for r in results)
        total = level * args.turns
        report["levels"][str(level)] = {
            "turns": len(lat),
            "errors": err,
            "p50_ms": round(statistics.median(lat), 1) if lat else 0,
            "p95_ms": round(_pct(lat, 95), 1) if lat else 0,
            "max_ms": round(max(lat), 1) if lat else 0,
        }
        s = report["levels"][str(level)]
        print(
            f"level={level}: turns={s['turns']}/{total} errors={err} "
            f"p50={s['p50_ms']}ms p95={s['p95_ms']}ms max={s['max_ms']}ms",
            flush=True,
        )
    out = _ROOT / ".run" / "capacity_probe.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
