#!/usr/bin/env python3
"""Benchmark Semantic Kernel latency on unique Russian utterances."""

from __future__ import annotations

import os
import statistics
import time

from packages.dialogue_engine.semantic_kernel.kernel import interpret
from packages.dialogue_engine.semantic_kernel.morphology import normalize_token

SUBJECTS = ("", "У меня ", "У мужа ", "У мамы ", "У коллеги ")
ISSUES = (
    "голова болит",
    "локоть ноет",
    "першит в горле",
    "тошнит",
    "живот урчит",
    "спина ломит",
    "ухо заложило",
    "колено тянет",
)
TEMPORAL = (
    "",
    " с утра",
    " вчера",
    " второй день",
    " уже пятый час",
    " сейчас уже лучше",
)
NEGATION = ("", " не ")
REFERENCES = ("", "Это ", "Сейчас уже лучше. ")


def generate_unique_utterances(limit: int = 1200) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for subj in SUBJECTS:
        for issue in ISSUES:
            for temp in TEMPORAL:
                for neg in NEGATION:
                    text = f"{subj}{neg}{issue}{temp}".strip()
                    if text and text not in seen:
                        seen.add(text)
                        out.append(text)
                    if len(out) >= limit:
                        return out
    for ref in REFERENCES:
        for temp in ("вчера началось", "пятый час", "плохо спал"):
            text = f"{ref}{temp}".strip()
            if text not in seen:
                seen.add(text)
                out.append(text)
    while len(out) < limit:
        i = len(out)
        text = f"беспокоит область {i} уже {i % 7} день"
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out[:limit]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    idx = int(len(values) * pct)
    idx = min(idx, len(values) - 1)
    return values[idx]


def main() -> None:
    samples = generate_unique_utterances(1000)
    mode = "pymorphy3" if os.environ.get("IMVERA_SEMANTIC_NO_MORPH") != "1" else "fallback"

    # cold start
    cold_start = (time.perf_counter() - time.perf_counter())
    t0 = time.perf_counter()
    interpret("прогрев", utterance_id="warmup")
    normalize_token("прогрев")
    cold_start = (time.perf_counter() - t0) * 1000

    times: list[float] = []
    for i, text in enumerate(samples):
        t0 = time.perf_counter()
        interpret(text, utterance_id=f"bench-{i}")
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    n = len(times)
    print(f"mode={mode}")
    print(f"unique_n={n}")
    print(f"cold_start_ms={cold_start:.2f}")
    print(f"p50={statistics.median(times):.2f}ms")
    print(f"p95={percentile(times, 0.95):.2f}ms")
    print(f"p99={percentile(times, 0.99):.2f}ms")
    print(f"max={max(times):.2f}ms")


if __name__ == "__main__":
    main()
