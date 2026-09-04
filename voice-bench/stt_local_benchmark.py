#!/usr/bin/env python3
"""Local STT benchmark scaffold — GigaAM vs Qwen3-ASR vs current (Phase 6).

Usage:
    python3 voice-bench/stt_local_benchmark.py --wav-dir ./corpus --strict

When models are unavailable the harness still runs structure checks and
reports SKIPPED backends with zero WER/latency placeholders.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass
class SttBenchResult:
    backend: str
    wer: Optional[float] = None
    latency_ms_p50: Optional[float] = None
    latency_ms_p90: Optional[float] = None
    files: int = 0
    skipped: bool = False
    note: str = ""


@dataclass
class SttBenchmarkReport:
    results: List[SttBenchResult] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "results": [
                {
                    "backend": r.backend,
                    "wer": r.wer,
                    "latency_ms_p50": r.latency_ms_p50,
                    "latency_ms_p90": r.latency_ms_p90,
                    "files": r.files,
                    "skipped": r.skipped,
                    "note": r.note,
                }
                for r in self.results
            ]
        }


def _list_wavs(wav_dir: str) -> List[str]:
    out: List[str] = []
    for root, _dirs, files in os.walk(wav_dir):
        for name in files:
            if name.lower().endswith(".wav"):
                out.append(os.path.join(root, name))
    return sorted(out)


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * pct))
    return ordered[max(0, min(idx, len(ordered) - 1))]


def _bench_backend(name: str, wavs: Sequence[str]) -> SttBenchResult:
    """Run one backend or return structured skip when unavailable."""
    if name == "current":
        try:
            sys.path.insert(0, os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "telephony",
            ))
            from adapters.stt import STTEngine  # type: ignore
            engine = STTEngine()
        except Exception as exc:  # noqa: BLE001
            return SttBenchResult(
                backend=name,
                skipped=True,
                note=f"unavailable: {exc}",
            )
        latencies: List[float] = []
        for path in wavs[:20]:
            t0 = time.perf_counter()
            try:
                engine.transcribe(path)
            except Exception:  # noqa: BLE001
                continue
            latencies.append((time.perf_counter() - t0) * 1000.0)
        return SttBenchResult(
            backend=name,
            wer=None,
            latency_ms_p50=_percentile(latencies, 0.5),
            latency_ms_p90=_percentile(latencies, 0.9),
            files=len(latencies),
            note="WER requires reference transcripts JSON",
        )
    if name in ("gigaam-v3-rnnt", "qwen3-asr"):
        return SttBenchResult(
            backend=name,
            skipped=True,
            note="model host not configured in this session",
        )
    return SttBenchResult(backend=name, skipped=True, note="unknown backend")


def run_benchmark(wav_dir: str, backends: Sequence[str]) -> SttBenchmarkReport:
    wavs = _list_wavs(wav_dir)
    report = SttBenchmarkReport()
    for backend in backends:
        report.results.append(_bench_backend(backend, wavs))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav-dir", default="voice-bench/corpus")
    parser.add_argument(
        "--backends",
        default="current,gigaam-v3-rnnt,qwen3-asr",
        help="comma-separated backend ids",
    )
    parser.add_argument("--out", default="voice-bench/reports/stt_local_benchmark.json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    backends = [b.strip() for b in args.backends.split(",") if b.strip()]
    if not os.path.isdir(args.wav_dir):
        print(f"wav dir missing: {args.wav_dir}", file=sys.stderr)
        return 1 if args.strict else 0
    report = run_benchmark(args.wav_dir, backends)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)
    ran = sum(1 for r in report.results if not r.skipped)
    print(f"STT benchmark: {ran}/{len(report.results)} backends exercised")
    for r in report.results:
        status = "SKIP" if r.skipped else "OK"
        print(f"  {status} {r.backend}: {r.note or r.latency_ms_p50}")
    if args.strict and ran == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
