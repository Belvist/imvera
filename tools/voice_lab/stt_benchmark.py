#!/usr/bin/env python3
"""STT benchmark on real phone WAV dumps — GigaAM variants, no prod config change."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DEFAULT = Path(__file__).resolve().parent / "fixtures" / "stt_phone" / "manifest.jsonl"


@dataclass
class SampleResult:
    wav_path: str
    call_id: str
    utterance_id: str
    bucket: str
    expected_text: str
    recognized_text: str
    latency_ms: int
    audio_duration_ms: int
    rtf: float
    wer: float | None
    cer: float | None
    error: str = ""


@dataclass
class ConfigResult:
    model_id: str
    device: str
    cold_ms: int = 0
    samples: list[SampleResult] = field(default_factory=list)
    failures: int = 0

    @property
    def warm_latencies(self) -> list[int]:
        return [s.latency_ms for s in self.samples if not s.error and s.latency_ms > 0]

    def summary(self) -> dict:
        lats = self.warm_latencies
        wers = [s.wer for s in self.samples if s.wer is not None]
        cers = [s.cer for s in self.samples if s.cer is not None]
        return {
            "model_id": self.model_id,
            "device": self.device,
            "cold_ms": self.cold_ms,
            "n_samples": len(self.samples),
            "failures": self.failures,
            "warm_p50_ms": int(statistics.median(lats)) if lats else None,
            "warm_p95_ms": int(statistics.quantiles(lats, n=20)[-1]) if len(lats) >= 2 else (lats[0] if lats else None),
            "wer_mean": round(statistics.mean(wers), 4) if wers else None,
            "cer_mean": round(statistics.mean(cers), 4) if cers else None,
            "rtf_mean": round(
                statistics.mean([s.rtf for s in self.samples if not s.error and s.rtf > 0]),
                4,
            )
            if any(not s.error for s in self.samples)
            else None,
        }


def _normalize(text: str) -> str:
    import re

    t = (text or "").lower().strip()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _wer_cer(expected: str, got: str) -> tuple[float | None, float | None]:
    exp = _normalize(expected)
    rec = _normalize(got)
    if not exp:
        return None, None
    exp_words = exp.split()
    rec_words = rec.split()
    if not exp_words:
        return None, None
    wer = _levenshtein(exp_words, rec_words) / len(exp_words)
    cer = _levenshtein(exp, rec) / max(len(exp), 1)
    return round(wer, 4), round(cer, 4)


def _wav_duration_ms(path: Path) -> int:
    with wave.open(str(path)) as wf:
        return int(wf.getnframes() / wf.getframerate() * 1000)


def _load_manifest(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _collect_wavs(dump_dir: Path, manifest_rows: list[dict]) -> list[dict]:
    by_path: dict[str, dict] = {}
    for row in manifest_rows:
        wav = row.get("wav_path")
        if wav:
            by_path[str(Path(wav))] = row
    if dump_dir.is_dir():
        for wav in sorted(dump_dir.glob("*.wav")):
            key = str(wav)
            meta = by_path.get(key, {})
            call_id, utterance_id = _split_wav_name(wav)
            by_path.setdefault(
                key,
                {
                    "wav_path": key,
                    "call_id": meta.get("call_id") or call_id,
                    "utterance_id": meta.get("utterance_id") or utterance_id,
                    "expected_text": meta.get("expected_text", ""),
                    "bucket": meta.get("bucket", "unknown"),
                },
            )
    return list(by_path.values())


def _split_wav_name(path: Path) -> tuple[str, str]:
    stem = path.stem
    if "_" in stem:
        call_id, utterance_id = stem.rsplit("_", 1)
        return call_id, utterance_id
    return stem, ""


def _load_engine(model_id: str, device: str):
    from services.stt.gigaam_engine import load_gigaam_engine

    return load_gigaam_engine(
        {
            "id": model_id,
            "device": device,
            "fp16_encoder": device != "cpu",
            "use_flash": False,
        }
    )


def _transcribe(engine, wav_path: Path) -> tuple[str, int]:
    started = time.monotonic()
    text = engine.transcribe_wav(wav_path)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return text, elapsed_ms


def run_config(model_id: str, device: str, items: list[dict]) -> ConfigResult:
    result = ConfigResult(model_id=model_id, device=device)
    try:
        engine = _load_engine(model_id, device)
    except Exception as exc:
        result.failures = len(items)
        for item in items:
            result.samples.append(
                SampleResult(
                    wav_path=item["wav_path"],
                    call_id=str(item.get("call_id") or ""),
                    utterance_id=str(item.get("utterance_id") or ""),
                    bucket=str(item.get("bucket") or "unknown"),
                    expected_text=str(item.get("expected_text") or ""),
                    recognized_text="",
                    latency_ms=0,
                    audio_duration_ms=0,
                    rtf=0.0,
                    wer=None,
                    cer=None,
                    error=f"load_failed: {exc}",
                )
            )
        return result

    # Cold start on first file.
    first = Path(items[0]["wav_path"])
    try:
        text, cold_ms = _transcribe(engine, first)
        result.cold_ms = cold_ms
        dur = _wav_duration_ms(first)
        exp = str(items[0].get("expected_text") or "")
        wer, cer = _wer_cer(exp, text) if exp else (None, None)
        result.samples.append(
            SampleResult(
                wav_path=str(first),
                call_id=str(items[0].get("call_id") or ""),
                utterance_id=str(items[0].get("utterance_id") or ""),
                bucket=str(items[0].get("bucket") or "unknown"),
                expected_text=exp,
                recognized_text=text,
                latency_ms=cold_ms,
                audio_duration_ms=dur,
                rtf=round(cold_ms / max(dur, 1), 4),
                wer=wer,
                cer=cer,
            )
        )
        start_idx = 1
    except Exception as exc:
        result.cold_ms = -1
        result.failures += 1
        result.samples.append(
            SampleResult(
                wav_path=str(first),
                call_id=str(items[0].get("call_id") or ""),
                utterance_id=str(items[0].get("utterance_id") or ""),
                bucket=str(items[0].get("bucket") or "unknown"),
                expected_text=str(items[0].get("expected_text") or ""),
                recognized_text="",
                latency_ms=0,
                audio_duration_ms=_wav_duration_ms(first),
                rtf=0.0,
                wer=None,
                cer=None,
                error=f"cold_failed: {exc}",
            )
        )
        start_idx = 1

    for item in items[start_idx:]:
        wav = Path(item["wav_path"])
        dur = _wav_duration_ms(wav)
        try:
            text, latency_ms = _transcribe(engine, wav)
            exp = str(item.get("expected_text") or "")
            wer, cer = _wer_cer(exp, text) if exp else (None, None)
            result.samples.append(
                SampleResult(
                    wav_path=str(wav),
                    call_id=str(item.get("call_id") or ""),
                    utterance_id=str(item.get("utterance_id") or ""),
                    bucket=str(item.get("bucket") or "unknown"),
                    expected_text=exp,
                    recognized_text=text,
                    latency_ms=latency_ms,
                    audio_duration_ms=dur,
                    rtf=round(latency_ms / max(dur, 1), 4),
                    wer=wer,
                    cer=cer,
                )
            )
        except Exception as exc:
            result.failures += 1
            result.samples.append(
                SampleResult(
                    wav_path=str(wav),
                    call_id=str(item.get("call_id") or ""),
                    utterance_id=str(item.get("utterance_id") or ""),
                    bucket=str(item.get("bucket") or "unknown"),
                    expected_text=str(item.get("expected_text") or ""),
                    recognized_text="",
                    latency_ms=0,
                    audio_duration_ms=dur,
                    rtf=0.0,
                    wer=None,
                    cer=None,
                    error=str(exc),
                )
            )
    return result


def _print_table(summaries: list[dict]) -> None:
    headers = [
        "model",
        "device",
        "cold_ms",
        "p50_ms",
        "p95_ms",
        "wer",
        "cer",
        "rtf",
        "fail",
        "n",
    ]
    print("\n" + " | ".join(headers))
    print("-" * 90)
    for row in summaries:
        print(
            " | ".join(
                [
                    str(row.get("model_id", "")),
                    str(row.get("device", "")),
                    str(row.get("cold_ms", "")),
                    str(row.get("warm_p50_ms", "")),
                    str(row.get("warm_p95_ms", "")),
                    str(row.get("wer_mean", "")),
                    str(row.get("cer_mean", "")),
                    str(row.get("rtf_mean", "")),
                    str(row.get("failures", "")),
                    str(row.get("n_samples", "")),
                ]
            )
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark GigaAM on phone STT dumps")
    parser.add_argument(
        "--dump-dir",
        type=Path,
        default=ROOT / ".run" / "stt_dumps",
        help="Directory with call_id_u-N.wav files",
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST_DEFAULT)
    parser.add_argument(
        "--models",
        nargs="*",
        default=["v3_e2e_rnnt", "v3_rnnt"],
        help="GigaAM model ids",
    )
    parser.add_argument(
        "--devices",
        nargs="*",
        default=["cpu"],
        help="cpu and/or mps (mps attempted only if listed)",
    )
    parser.add_argument("--json-out", type=Path, default=ROOT / ".run" / "stt_benchmark.json")
    args = parser.parse_args(argv)

    manifest_rows = _load_manifest(args.manifest)
    items = _collect_wavs(args.dump_dir, manifest_rows)
    if not items:
        print(f"No WAV files in {args.dump_dir}")
        return 1

    configs: list[ConfigResult] = []
    for model_id in args.models:
        for device in args.devices:
            print(f"Running {model_id} @ {device} ({len(items)} files)...")
            configs.append(run_config(model_id, device, items))

    summaries = [c.summary() for c in configs]
    report = {
        "dump_dir": str(args.dump_dir),
        "manifest": str(args.manifest),
        "n_files": len(items),
        "summaries": summaries,
        "details": [
            {
                "model_id": c.model_id,
                "device": c.device,
                "samples": [s.__dict__ for s in c.samples],
            }
            for c in configs
        ],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_table(summaries)
    print(f"\nWrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
