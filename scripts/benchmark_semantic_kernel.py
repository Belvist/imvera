#!/usr/bin/env python3
"""Benchmark Semantic Kernel latency on Russian utterances."""

from __future__ import annotations

import statistics
import time

from packages.dialogue_engine.semantic_kernel.kernel import interpret

SAMPLES = [
    "угу",
    "да",
    "нормально",
    "Голова болит с утра",
    "локоть ноет",
    "онемел палец",
    "шею тянет",
    "першит в горле",
    "ухо заложило",
    "тяжесть в груди",
    "колено второй день тянет",
    "У мужа болит сердце",
    "Вчера болела голова, сегодня нормально",
    "Нет, не с утра. Со вчера.",
    "Что-то там опять прихватило",
    "Нормально. А вы кто? И колено второй день тянет.",
] * 63  # ~1008


def main() -> None:
    times: list[float] = []
    for i, text in enumerate(SAMPLES[:1000]):
        t0 = time.perf_counter()
        interpret(text, utterance_id=f"bench-{i}")
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    n = len(times)
    print(f"n={n}")
    print(f"p50={statistics.median(times):.2f}ms")
    print(f"p95={times[int(n * 0.95)]:.2f}ms")
    print(f"p99={times[int(n * 0.99)]:.2f}ms")
    print(f"max={max(times):.2f}ms")


if __name__ == "__main__":
    main()
