#!/usr/bin/env python3
"""F8 latency baseline harness — first_audio p50/p95 per dialogue turn.

Measures end-to-end latency from speech_end to first audible Vera frame,
aligned with ENGINEERING_PLAN.md §14–15 (STT → plan → TTS first sentence).

Modes
-----
  synthetic (default)  plan_reply + optional real STT/TTS; always runnable offline
  e2e                  full ``process_turn_stream`` (phone path, segment_dir set)
  parse                ingest ``[call-agent] LATENCY`` lines from logs

Usage
-----
    python3 voice-lab/latency_baseline.py
    python3 voice-lab/latency_baseline.py --mode e2e --trials 5
    python3 voice-lab/latency_baseline.py --real-stt --real-tts
    python3 voice-lab/latency_baseline.py --parse docker.log
    python3 voice-lab/latency_baseline.py --json-out voice-lab/reports/latency_baseline.json

Gates (ENGINEERING_PLAN §15.4, read.md pilot targets)
-----
  CPU: first_audio p50 ≤ 4000 ms
  GPU: first_audio p50 ≤ 2000 ms (future stack)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import struct
import sys
import tempfile
import time
import wave
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_TELEPHONY = os.path.join(_ROOT, "telephony")
_RUNTIME = os.path.join(_ROOT, "runtime", "scripts")
sys.path.insert(0, _TELEPHONY)
sys.path.insert(0, _RUNTIME)

# Default phone-path endpointing tail (Lua waits for silence before POST).
DEFAULT_ENDPOINTING_MS = int(os.environ.get("MOSS_ENDPOINTING_MS", "2000"))

# Product gates from ENGINEERING_PLAN §15.4 / Track B plan.
GATE_CPU_FIRST_AUDIO_MS = 4000
GATE_GPU_FIRST_AUDIO_MS = 2000

DEFAULT_PHRASES = [
    "Нормально, спасибо.",
    "Голова немного болит.",
    "Спал плохо, просыпался.",
    "Да, всё хорошо.",
    "Настроение нормальное.",
]

LATENCY_RE = re.compile(
    r"\[call-agent\] LATENCY (\S+): turn=(\d+) gen=(\d+) "
    r"stt=(\d+) plan=(\d+) gen\+tts=(\d+) first_audio=(\d+)"
)


@dataclass
class StageTiming:
    """One measured turn; all ms relative to speech_end (t0)."""

    endpointing_ms: float = 0.0
    stt_ms: float = 0.0
    plan_ms: float = 0.0
    gen_tts_ms: float = 0.0
    first_audio_ms: float = 0.0
    transcript: str = ""
    reply_preview: str = ""
    mode: str = "synthetic"
    phrase: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BaselineReport:
    generated_at: str
    mode: str
    trials: int
    endpointing_ms: int
    stack: Dict[str, Any] = field(default_factory=dict)
    samples: List[Dict[str, Any]] = field(default_factory=list)
    aggregates: Dict[str, Any] = field(default_factory=dict)
    gates: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (p / 100.0)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(ordered[lo])
    frac = rank - lo
    return float(ordered[lo] * (1.0 - frac) + ordered[hi] * frac)


def _aggregate(samples: List[StageTiming]) -> Dict[str, Any]:
    def col(name: str) -> List[float]:
        return [float(getattr(s, name)) for s in samples]

    out: Dict[str, Any] = {"count": len(samples)}
    for key in ("endpointing_ms", "stt_ms", "plan_ms", "gen_tts_ms", "first_audio_ms"):
        vals = col(key)
        if not vals:
            continue
        out[key] = {
            "min": min(vals),
            "max": max(vals),
            "mean": statistics.mean(vals),
            "p50": _percentile(vals, 50),
            "p95": _percentile(vals, 95),
        }
    return out


def _gate_check(aggregates: Dict[str, Any]) -> Dict[str, Any]:
    fa = aggregates.get("first_audio_ms", {})
    p50 = fa.get("p50", 0.0)
    p95 = fa.get("p95", 0.0)
    return {
        "cpu_first_audio_p50_ms": GATE_CPU_FIRST_AUDIO_MS,
        "cpu_first_audio_p95_ms": GATE_CPU_FIRST_AUDIO_MS,
        "gpu_first_audio_p50_ms": GATE_GPU_FIRST_AUDIO_MS,
        "pass_cpu_p50": p50 <= GATE_CPU_FIRST_AUDIO_MS if p50 else None,
        "pass_cpu_p95": p95 <= GATE_CPU_FIRST_AUDIO_MS if p95 else None,
        "pass_gpu_p50": p50 <= GATE_GPU_FIRST_AUDIO_MS if p50 else None,
        "measured_p50_ms": p50,
        "measured_p95_ms": p95,
    }


def make_speech_wav(
    path: str,
    *,
    duration_s: float = 2.5,
    sample_rate: int = 16000,
    amplitude: int = 4000,
) -> None:
    """Short synthetic utterance with enough energy for the STT precheck."""
    n = int(sample_rate * duration_s)
    # mix tone + noise so energy gate passes without being pure silence
    samples = []
    for i in range(n):
        tone = int(amplitude * math.sin(2 * math.pi * 220 * i / sample_rate))
        noise = ((i * 17) % 97) - 48
        samples.append(max(-32767, min(32767, tone + noise)))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack("<%dh" % n, *samples))


class _MockSTT:
    """Instant STT for offline synthetic runs."""

    def ready(self) -> bool:
        return True

    def transcribe_with_confidence(self, _path: str):
        return type("R", (), {"text": "нормально спасибо", "confidence": 0.92})()

    def transcribe(self, _path: str) -> str:
        return "нормально спасибо"


class _MockTTS:
    """Minimal TTS stream yielding one audio frame."""

    def ready(self) -> bool:
        return True

    def cancel_stream_by_id(self, _sid: str) -> None:
        pass

    def stream(self, text, cancel_event=None, stream_id=None):
        import base64
        import io

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(struct.pack("<800h", *([1200] * 800)))
        yield {"i": 0, "wav_b64": base64.b64encode(buf.getvalue()).decode()}
        yield {"done": True}


def _build_serve():
    from core.orchestrator import Serve

    class _Args:
        refs: list = []
        tts_port_file = None
        tts_port = None
        inference_steps = 6
        no_style = False
        outdir = tempfile.mkdtemp(prefix="moss_latency_")
        tts_host = os.environ.get("MOSS_TTS_HOST")

    serve = Serve(_Args())
    return serve


def _probe_stack(serve) -> Dict[str, Any]:
    stt_ok = bool(getattr(serve.stt, "ready", lambda: False)())
    tts_ok = bool(getattr(serve.tts, "ready", lambda: False)())
    llm_ok = bool(getattr(serve.llm, "ready", lambda: False)())
    return {
        "stt_ready": stt_ok,
        "tts_ready": tts_ok,
        "llm_ready": llm_ok,
        "stt_host": os.environ.get("MOSS_STT_HOST", ""),
        "stt_model": os.environ.get("MOSS_STT_TRANSFORMERS_MODEL", ""),
        "llm_provider": os.environ.get("MOSS_LLM_PROVIDER", "local"),
    }


def measure_synthetic_turn(
    serve,
    phrase: str,
    *,
    endpointing_ms: int,
    use_real_stt: bool,
    use_real_tts: bool,
    wav_path: str,
) -> StageTiming:
    """Time plan + (mock or real) STT/TTS without network I/O for dialogue."""
    from tests.live_call_sim import live_turn

    timing = StageTiming(
        endpointing_ms=float(endpointing_ms),
        phrase=phrase,
        mode="synthetic",
    )
    t0 = time.time()

    # STT (optional real)
    t_stt0 = time.time()
    if use_real_stt and getattr(serve.stt, "ready", lambda: False)():
        res = serve.stt.transcribe_with_confidence(wav_path)
        transcript = res.text or phrase
        timing.stt_ms = (time.time() - t_stt0) * 1000.0
    else:
        transcript = phrase
        timing.stt_ms = 1.0  # mock decode

    # plan_reply (prod path via live_call_sim)
    t_plan0 = time.time()
    cid = serve.new_call(caller_id="+79001234567")
    agent = serve.get_call(cid).agent
    agent.start_check_in()
    plan, spoken = live_turn(agent, transcript, confidence=0.85)
    timing.plan_ms = (time.time() - t_plan0) * 1000.0
    timing.transcript = transcript
    timing.reply_preview = (spoken or "")[:120]

    # TTS first frame (optional real)
    t_tts0 = time.time()
    text = spoken or plan.get("fallback") or "Понятно."
    if use_real_tts and getattr(serve.tts, "ready", lambda: False)():
        got = False
        for frame in serve.tts.stream(text):
            if frame.get("wav_b64"):
                got = True
                break
            if frame.get("done"):
                break
        if not got:
            _MockTTS().stream(text)
    else:
        next(_MockTTS().stream(text))
    timing.gen_tts_ms = (time.time() - t_tts0) * 1000.0

    timing.first_audio_ms = (
        timing.endpointing_ms + timing.stt_ms + timing.plan_ms + timing.gen_tts_ms
    )
    serve.end_call(cid)
    _ = t0  # speech_end anchor
    return timing


def measure_e2e_turn(
    serve,
    wav_path: str,
    *,
    endpointing_ms: int,
    phrase: str,
) -> StageTiming:
    """Full phone-path ``process_turn_stream`` with segment_dir."""
    import shutil

    timing = StageTiming(
        endpointing_ms=float(endpointing_ms),
        phrase=phrase,
        mode="e2e",
    )
    cid = serve.new_call(caller_id="+79001234567")
    ctx = serve.get_call(cid)
    ctx.agent.start_check_in()
    ctx = serve.begin_turn(cid)
    seg_dir = tempfile.mkdtemp(prefix="moss_latency_seg_")

    t0 = time.time()
    first_audio_at: Optional[float] = None
    stt_done_at: Optional[float] = None
    plan_done_at: Optional[float] = None
    transcript = ""
    reply = ""

    try:
        for frame in serve.process_turn_stream(
            wav_path, call_id=cid, segment_dir=seg_dir
        ):
            now = time.time()
            if frame.get("transcript"):
                transcript = frame.get("transcript") or transcript
            if frame.get("reply"):
                reply = frame.get("reply") or reply
            if frame.get("seg_file") or frame.get("wav_b64"):
                if first_audio_at is None:
                    first_audio_at = now
            if stt_done_at is None and frame.get("type") == "interim" and frame.get("final"):
                stt_done_at = now
                plan_done_at = now
    finally:
        serve.end_turn(ctx)
        serve.end_call(cid)
        shutil.rmtree(seg_dir, ignore_errors=True)

    speech_end = t0 + (endpointing_ms / 1000.0)
    if stt_done_at:
        timing.stt_ms = max(0.0, (stt_done_at - speech_end) * 1000.0)
    if plan_done_at and stt_done_at:
        timing.plan_ms = max(0.0, (plan_done_at - stt_done_at) * 1000.0)
    if first_audio_at:
        timing.gen_tts_ms = max(0.0, (first_audio_at - (plan_done_at or speech_end)) * 1000.0)
        timing.first_audio_ms = max(0.0, (first_audio_at - speech_end) * 1000.0)
    else:
        timing.first_audio_ms = (time.time() - speech_end) * 1000.0

    timing.transcript = transcript or ""
    timing.reply_preview = (reply or "")[:120]
    return timing


def parse_latency_logs(path: str) -> List[StageTiming]:
    """Parse orchestrator LATENCY trace lines (live / docker logs)."""
    samples: List[StageTiming] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LATENCY_RE.search(line)
            if not m:
                continue
            _cid, _turn, _gen, stt, plan, gen_tts, first_audio = m.groups()
            samples.append(
                StageTiming(
                    endpointing_ms=0.0,
                    stt_ms=float(stt),
                    plan_ms=float(plan),
                    gen_tts_ms=float(gen_tts),
                    first_audio_ms=float(first_audio),
                    mode="parse",
                )
            )
    return samples


def render_markdown(report: BaselineReport) -> str:
    agg = report.aggregates
    gates = report.gates
    fa = agg.get("first_audio_ms", {})
    lines = [
        f"# Latency baseline (F8) — {report.generated_at}",
        "",
        f"- **Mode:** `{report.mode}`",
        f"- **Trials:** {report.trials}",
        f"- **Endpointing model:** {report.endpointing_ms} ms (speech_end delay before STT)",
        "",
        "## Stack probe",
        "",
        "```json",
        json.dumps(report.stack, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Aggregates (ms)",
        "",
        "| Stage | p50 | p95 | mean | min | max |",
        "|-------|-----|-----|------|-----|-----|",
    ]
    for stage in ("endpointing_ms", "stt_ms", "plan_ms", "gen_tts_ms", "first_audio_ms"):
        row = agg.get(stage, {})
        if not row:
            continue
        lines.append(
            f"| {stage} | {row.get('p50', 0):.0f} | {row.get('p95', 0):.0f} | "
            f"{row.get('mean', 0):.0f} | {row.get('min', 0):.0f} | {row.get('max', 0):.0f} |"
        )
    lines.extend([
        "",
        "## Gates",
        "",
        f"- CPU first_audio p50 gate: **≤ {gates.get('cpu_first_audio_p50_ms')} ms** — "
        f"measured **{gates.get('measured_p50_ms', 0):.0f} ms** "
        f"({'PASS' if gates.get('pass_cpu_p50') else 'FAIL' if gates.get('pass_cpu_p50') is not None else 'n/a'})",
        f"- CPU first_audio p95 gate: **≤ {gates.get('cpu_first_audio_p95_ms')} ms** — "
        f"measured **{gates.get('measured_p95_ms', 0):.0f} ms** "
        f"({'PASS' if gates.get('pass_cpu_p95') else 'FAIL' if gates.get('pass_cpu_p95') is not None else 'n/a'})",
        f"- GPU target p50: **≤ {gates.get('gpu_first_audio_p50_ms')} ms** "
        f"({'PASS' if gates.get('pass_gpu_p50') else 'FAIL' if gates.get('pass_gpu_p50') is not None else 'n/a'})",
        "",
        "## Methodology",
        "",
        "Aligned with `ENGINEERING_PLAN.md` §14–15:",
        "",
        "1. **speech_end** — caller stops speaking (+ modeled endpointing tail on phone path)",
        "2. **stt_ms** — `transcribe_with_confidence` (phone) or hop stream (WebApp)",
        "3. **plan_ms** — `plan_reply` FSM (deterministic, no LLM lock)",
        "4. **gen+tts_ms** — first LLM sentence + TTS first frame (`seg-0001.wav` or `wav_b64`)",
        "5. **first_audio** — sum to first audible Vera output",
        "",
        "Live production logs emit the same breakdown:",
        "`[call-agent] LATENCY <call_id>: stt=… plan=… gen+tts=… first_audio=…`",
        "",
    ])
    return "\n".join(lines)


def run_baseline(args: argparse.Namespace) -> BaselineReport:
    if args.mode == "parse":
        samples = parse_latency_logs(args.parse)
        if not samples:
            raise SystemExit(f"No LATENCY lines found in {args.parse}")
        mode = "parse"
        stack: Dict[str, Any] = {"source": args.parse}
    else:
        serve = _build_serve()
        stack = _probe_stack(serve)
        use_real_stt = args.real_stt or args.mode == "e2e"
        use_real_tts = args.real_tts or args.mode == "e2e"
        if args.mode == "e2e" and not (stack["stt_ready"] and stack["tts_ready"]):
            print(
                "[latency_baseline] WARN: e2e requested but STT/TTS not ready; "
                "injecting mocks (results are not production baseline)",
                file=sys.stderr,
            )
            if not stack["stt_ready"]:
                serve.stt = _MockSTT()
            if not stack["tts_ready"]:
                serve.tts = _MockTTS()

        phrases = args.phrases or DEFAULT_PHRASES
        samples = []
        fd, wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            make_speech_wav(wav_path, duration_s=args.wav_seconds)
            for i in range(args.trials):
                phrase = phrases[i % len(phrases)]
                if args.mode == "e2e":
                    samples.append(
                        measure_e2e_turn(
                            serve,
                            wav_path,
                            endpointing_ms=args.endpointing_ms,
                            phrase=phrase,
                        )
                    )
                else:
                    samples.append(
                        measure_synthetic_turn(
                            serve,
                            phrase,
                            endpointing_ms=args.endpointing_ms,
                            use_real_stt=use_real_stt,
                            use_real_tts=use_real_tts,
                            wav_path=wav_path,
                        )
                    )
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass
        mode = args.mode

    aggregates = _aggregate(samples)
    gates = _gate_check(aggregates)
    report = BaselineReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        mode=mode,
        trials=len(samples),
        endpointing_ms=args.endpointing_ms,
        stack=stack,
        samples=[s.to_dict() for s in samples],
        aggregates=aggregates,
        gates=gates,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--mode",
        choices=("synthetic", "e2e", "parse"),
        default="synthetic",
        help="synthetic=offline dialogue path; e2e=process_turn_stream; parse=log ingest",
    )
    parser.add_argument("--trials", type=int, default=5, help="number of turns to measure")
    parser.add_argument(
        "--endpointing-ms",
        type=int,
        default=DEFAULT_ENDPOINTING_MS,
        help="modeled post-speech silence before STT (phone path)",
    )
    parser.add_argument("--wav-seconds", type=float, default=2.5, help="synthetic utterance length")
    parser.add_argument("--real-stt", action="store_true", help="use live STT if ready")
    parser.add_argument("--real-tts", action="store_true", help="use live TTS if ready")
    parser.add_argument("--parse", metavar="LOGFILE", help="parse LATENCY lines (sets --mode parse)")
    parser.add_argument(
        "--json-out",
        default=os.path.join(_HERE, "reports", "latency_baseline.json"),
    )
    parser.add_argument(
        "--md-out",
        default=os.path.join(_HERE, "reports", "latency_baseline.md"),
    )
    parser.add_argument("--phrases", nargs="*", help="override test phrases")
    args = parser.parse_args()
    if args.parse:
        args.mode = "parse"

    report = run_baseline(args)

    os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

    md = render_markdown(report)
    with open(args.md_out, "w", encoding="utf-8") as f:
        f.write(md)

    fa = report.aggregates.get("first_audio_ms", {})
    print(f"Mode: {report.mode}  trials: {report.trials}")
    print(f"first_audio p50={fa.get('p50', 0):.0f}ms  p95={fa.get('p95', 0):.0f}ms")
    print(f"CPU gate (≤{GATE_CPU_FIRST_AUDIO_MS}ms): "
          f"{'PASS' if report.gates.get('pass_cpu_p50') else 'FAIL'}")
    print(f"JSON: {args.json_out}")
    print(f"Markdown: {args.md_out}")
    return 0 if report.gates.get("pass_cpu_p50") is not False else 1


if __name__ == "__main__":
    sys.exit(main())
