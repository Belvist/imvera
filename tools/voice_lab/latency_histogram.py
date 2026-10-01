"""Latency histogram from call timelines (reviewer item 10).

Reads forensic trace JSONL (stage.timing with stage=timeline, or legacy timeline) and prints
p50/p95 per SLO segment. No live system needed.

Usage:
  python3 tools/voice_lab/latency_histogram.py .run/traces/*.jsonl
SLO reference: answer→playout p50 <1000ms, p95 <=2000ms (first turn).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SEGMENTS = (
    "seg_answer_to_stt_final_ms",
    "seg_stt_final_to_decision_ms",
    "seg_decision_to_tts_first_pcm_ms",
    "seg_tts_first_pcm_to_playout_ms",
    "seg_answer_to_playout_ms",
)


def _pct(data: list[float], q: float) -> float:
    if not data:
        return float("nan")
    s = sorted(data)
    return s[min(len(s) - 1, int(len(s) * q))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()
    buckets: dict[str, list[float]] = {s: [] for s in SEGMENTS}
    n = 0
    for pattern in args.files:
        for path in Path(".").glob(pattern) if any(
            c in pattern for c in "*?[]"
        ) else [Path(pattern)]:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = row.get("payload", row)
                if not (row.get("type") == "timeline" or (
                    row.get("type") == "stage.timing" and payload.get("stage") == "timeline"
                )):
                    continue
                n += 1
                for seg in SEGMENTS:
                    val = payload.get(seg)
                    if isinstance(val, (int, float)):
                        buckets[seg].append(float(val))
    print(f"timelines: {n}")
    for seg in SEGMENTS:
        vals = buckets[seg]
        if not vals:
            print(f"{seg}: no data")
            continue
        print(f"{seg}: n={len(vals)} p50={_pct(vals, .5):.0f}ms "
              f"p95={_pct(vals, .95):.0f}ms max={max(vals):.0f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
