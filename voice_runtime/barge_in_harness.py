#!/usr/bin/env python3
"""Offline barge-in harness (ROADMAP E1 stand-in for live 20/20).

Simulates agent playback while synthetic speech arrives; asserts
GenerationGuard bump completes within 300 ms wall time.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from media_adapter import StreamingPcmAdapter  # noqa: E402


def run_once(delay_ms=50) -> float:
    adapter = StreamingPcmAdapter(sample_rate=16000, pre_roll_ms=400)
    play_gid = adapter.generation.current()
    # Simulate playback in progress...
    time.sleep(delay_ms / 1000.0)
    # Speech onset → barge-in flush
    t0 = time.perf_counter()
    new_gid = adapter.generation.bump()
    # Drop stale: old gid must be invalid immediately
    assert not adapter.generation.is_current(play_gid)
    assert adapter.generation.is_current(new_gid)
    # Pre-roll should capture recent audio and flush cleanly
    adapter.push_frames([100] * 320)  # 20 ms
    flushed = adapter.pre_roll.flush()
    assert len(flushed) >= 320
    assert len(adapter.pre_roll) == 0
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return elapsed_ms


def main():
    trials = int(os.environ.get("MOSS_BARGE_TRIALS", "20"))
    budget_ms = float(os.environ.get("MOSS_BARGE_BUDGET_MS", "300"))
    times = []
    for i in range(trials):
        times.append(run_once(delay_ms=10 + (i % 5) * 5))
    worst = max(times)
    ok = worst <= budget_ms
    print(f"barge_in_harness trials={trials} worst_ms={worst:.2f} "
          f"budget_ms={budget_ms} {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
