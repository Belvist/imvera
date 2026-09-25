"""Latency probe: p50/p95 per provider + dialogue turn on the lab stack.

Usage:
    python3 scripts/latency_probe.py [--n 20]

Measures against the running local workers (STT :9101, TTS :9102,
LLM :9103) plus N dialogue turns through CallSession. Prints p50/p95
per stage and saves JSON to .run/latency_probe.json.

Honest labels: lab Mac, local workers, no PSTN. Compares against
PROJECT_CONTEXT.md targets (turn p50 < 1 s, p95 <= 2 s).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.contracts.semantic import TurnContext
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from services.llm.http_provider import HttpLLMProvider
from services.stt.http_provider import HttpSTTProvider
from services.tts.http_provider import HttpTTSProvider

PHRASE = "Здравствуйте, Тамара Юрьевна. Как вы себя чувствуете?"
TEXT = "Чувствую себя хорошо, спасибо."


def _pct(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = min(len(ordered) - 1, int(pct / 100 * len(ordered)))
    return ordered[idx]


async def _time(coro) -> float:
    t0 = time.perf_counter()
    await coro
    return (time.perf_counter() - t0) * 1000


async def _sample(out: list[float], failed: list[str], label: str, coro_fn) -> None:
    try:
        t0 = time.perf_counter()
        await coro_fn()
        out.append((time.perf_counter() - t0) * 1000)
    except Exception as exc:
        failed.append(f"{label}: {type(exc).__name__}")


async def main(n: int) -> dict:
    stt = HttpSTTProvider("http://127.0.0.1:9101")
    tts = HttpTTSProvider("http://127.0.0.1:9102")
    llm = HttpLLMProvider("http://127.0.0.1:9103")
    out: dict[str, list[float]] = {"tts_ms": [], "llm_ms": [], "stt_ms": [], "turn_ms": []}
    failed: list[str] = []

    # Warmup (cold model load excluded from stats).
    try:
        ctx0 = TurnContext(
            call_id="probe",
            turn_id=0,
            utterance_id="w",
            state_version=0,
            raw_text="тепло",
            asr_quality="GOOD",
            pending_question_id=None,
            pending_question=None,
            pending_question_delivery="complete",
        )
        await llm.interpret_turn(ctx0, deadline=time.monotonic() + 300)
    except Exception as exc:
        failed.append(f"warmup: {type(exc).__name__}")

    pcm = b""
    for _ in range(n):
        deadline = time.monotonic() + 60
        t0 = time.perf_counter()

        async def _drain_tts():
            chunks = []
            async for ch in tts.synthesize(
                PHRASE, call_id="probe", generation_id="g", phrase_id="p",
                deadline=deadline,
            ):
                chunks.append(ch.pcm_s16le)
            return b"".join(chunks)

        pcm = await _drain_tts()
        out["tts_ms"].append((time.perf_counter() - t0) * 1000)

    for _ in range(n):
        ctx = TurnContext(
            call_id="probe",
            turn_id=1,
            utterance_id="u",
            state_version=1,
            raw_text=TEXT,
            asr_quality="GOOD",
            pending_question_id=None,
            pending_question="Как вы себя чувствуете?",
            pending_question_delivery="complete",
        )

        async def _llm(ctx=ctx):
            await llm.interpret_turn(ctx, deadline=time.monotonic() + 120)

        await _sample(out["llm_ms"], failed, "llm", _llm)

    if pcm:
        for _ in range(n):

            async def _stt():
                await stt.transcribe_final(
                    pcm, 16000, call_id="probe", turn_id=1,
                    deadline=time.monotonic() + 120, utterance_id="u",
                )

            await _sample(out["stt_ms"], failed, "stt", _stt)

    session = CallSession(
        call_id="probe", family_id="f", store=InMemoryCallRecordStore()
    )
    session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    for text in (["хорошо", "нормально", "поела", "спал нормально"] * ((n // 4) + 1))[:n]:
        t0 = time.perf_counter()
        session.handle_user_text(text)
        out["turn_ms"].append((time.perf_counter() - t0) * 1000)

    summary = {"failed": failed}
    for k, v in out.items():
        summary[k] = {
            "n": len(v),
            "p50": round(statistics.median(v), 1) if v else 0.0,
            "p95": round(_pct(v, 95), 1),
            "max": round(max(v), 1) if v else 0.0,
        }
    path = _ROOT / ".run" / "latency_probe.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    args = ap.parse_args()
    summary = asyncio.run(main(args.n))
    for stage, s in summary.items():
        if stage == "failed":
            print(f"failed samples: {len(s)} {s[:5]}")
            continue
        flag = ""
        if stage == "turn_ms":
            flag = " (target p50<1000 p95<=2000: " + (
                "PASS" if s["p50"] < 1000 and s["p95"] <= 2000 else "FAIL") + ")"
        print(f"{stage}: n={s['n']} p50={s['p50']}ms p95={s['p95']}ms max={s['max']}ms{flag}")
    print("saved .run/latency_probe.json")
