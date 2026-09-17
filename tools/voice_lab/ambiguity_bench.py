"""Ambiguity bench — evidence for the tiny-model decision (ai-model-evaluation).

Freezes the hard cases where deterministic NLU is blind (short / unclear /
borderline turns from live fs-*.jsonl and the behavior fuzz pools) with an
expected route each. Measures, per candidate:

  accuracy on expected routes, p50/p95 latency, timeout/abstain rate.

Candidates:
  deterministic — current code, no model (baseline, always runs)
  tiny:<mlx-id> — packages.dialogue_engine.tinyllm.classify with IMVERA_TINYLLM_MODEL

Usage:
  python3 tools/voice_lab/ambiguity_bench.py
  IMVERA_TINYLLM_MODEL=mlx-community/SmolLM2-360M-Instruct-4bit \
    python3 tools/voice_lab/ambiguity_bench.py --models deterministic,tiny --repeat 3

A model is adopted only if it beats deterministic accuracy on this set
without breaking p95<=2s turn budget. No accuracy claim without this bench.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# (user text, pending question hint, expected route)
CASES: list[tuple[str, str | None, str]] = [
    # reluctance — tired / done
    ("Хватит уже.", "mood", "reluctance"),
    ("Ну всё, надоело.", "sleep", "reluctance"),
    ("Ой, давай уже заканчивать.", None, "reluctance"),
    ("Устал я говорить.", "mood", "reluctance"),
    ("Некогда мне.", "sleep", "reluctance"),
    ("Не знаю.", "background_medication", "reluctance"),
    ("Ага.", "background_mood", "reluctance"),
    ("Да вроде бы нет.", "important_to_share", "reluctance"),
    # repair — didn't hear
    ("Что?", "episode_onset", "repair"),
    ("Чего?", "episode_onset", "repair"),
    ("Алло.", "wellness", "reluctance"),
    ("Повторите.", "sleep", "repair"),
    # question_back
    ("А вы кто?", "wellness", "question_back"),
    ("Зачем звоните?", "mood", "question_back"),
    ("Про что ты?", "episode_onset", "question_back"),
    # hostile without content
    ("Не, это хуйня, ты сразу всё спросил.", "episode_onset", "hostile"),
    ("Ты дура.", "mood", "hostile"),
    # garbage / fragments
    ("Поднял.", "episode_onset", "reluctance"),
    # «Спали того.» carries a sleep fact in the real extractor — content,
    # clarified downstream, not debris.
    ("Спали того.", "wellness", "answer"),
    ("Пло.", "wellness", "reluctance"),
    ("Колю покушал когда?", "episode_onset", "garbage"),
    ("Э-э.", "mood", "reluctance"),
    # answers — must stay answers, never reluctance
    ("Хорошо.", "wellness", "answer"),
    ("Плохо.", "wellness", "answer"),
    ("Терпимая.", "episode_severity", "answer"),
    ("С утра.", "episode_onset", "answer"),
    ("Сейчас, я же говорю.", "episode_onset", "answer"),
    ("После еды.", "episode_onset", "answer"),
    ("Да, принял.", "background_medication", "answer"),
    ("Нет.", "important_to_share", "answer"),
    ("До свидания.", None, "reluctance"),
    ("Сердце болит, я падаю.", "wellness", "answer"),
]


@dataclass
class BenchResult:
    name: str
    accuracy: float
    p50_ms: float
    p95_ms: float
    abstain: int
    errors: list[str]


def _deterministic_route(text: str, pending: str | None) -> str:
    """The REAL pipeline: kernel turn + reluctance scorer (answers_pending)."""
    import uuid

    from packages.dialogue_engine.reluctance import (
        _IRRITATION,
    )
    from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

    t = (text or "").strip()
    if not t:
        return "unclear"
    turn = build_rich_turn_from_text(t, utterance_id=f"bench-{uuid.uuid4().hex[:6]}")
    if turn.control not in ("none", ""):
        # Controls end or redirect the call — reluctance-equivalent outcome.
        return "reluctance"
    if turn.user_question:
        return "question_back"
    if turn.dialogue_act == "repair":
        return "repair"
    if _IRRITATION.search(t):
        return "hostile"
    # Real scorer on a throwaway state (polarity/cooperation aware).
    from packages.dialogue_engine.reluctance import note_reluctance
    from packages.dialogue_engine.state import EngineState

    probe = EngineState(call_id="bench")
    if note_reluctance(probe, turn, answer_slot=pending, cooperative_fill=False) > 0:
        return "reluctance"
    if turn.issue_mentions or turn.goal_facts:
        return "answer"
    # Farewell and grounded short answers resolve in the live scheduler
    # (closing flow / slot extractors) — not garbage.
    if t.lower().rstrip(".!?") in {"до свидания", "пока", "всего доброго"}:
        return "answer"
    from packages.dialogue_engine.reluctance import _grounded_short_answer

    if _grounded_short_answer(t, pending):
        return "answer"
    # Content-free short turn with no signal: garbage/STT debris.
    return "garbage"


def run_deterministic() -> BenchResult:
    lat: list[float] = []
    bad: list[str] = []
    for text, pending, expected in CASES:
        t0 = time.monotonic()
        got = _deterministic_route(text, pending)
        lat.append((time.monotonic() - t0) * 1000)
        # garbage/unclear collapse to one bucket for the deterministic baseline
        norm = {"garbage": "garbage", "unclear": "garbage"}.get(got, got)
        exp = {"garbage": "garbage", "unclear": "garbage"}.get(expected, expected)
        if norm != exp:
            bad.append(f"{text!r}: got {got}, want {expected}")
    lat.sort()
    p50 = lat[len(lat) // 2]
    p95 = lat[int(len(lat) * 0.95)]
    return BenchResult("deterministic", 1 - len(bad) / len(CASES), p50, p95, 0, bad)


def run_tiny(model: str, repeat: int) -> BenchResult:
    import os

    if repeat <= 0:
        raise ValueError("repeat must be positive")
    os.environ["IMVERA_TINYLLM_MODEL"] = model
    from packages.dialogue_engine import tinyllm

    # route_clf backend has no warmup cost; MLX warms once (excluded).
    if model != "route_clf":
        tinyllm.classify("Проверка связи.", pending_question="wellness")
    lat: list[float] = []
    bad: list[str] = []
    abstain = 0
    for _ in range(repeat):
        for text, pending, expected in CASES:
            t0 = time.monotonic()
            got = tinyllm.classify(text, pending_question=pending)
            lat.append((time.monotonic() - t0) * 1000)
            if got is None:
                abstain += 1
                continue
            norm = {"garbage": "garbage", "unclear": "garbage"}.get(got, got)
            exp = {"garbage": "garbage", "unclear": "garbage"}.get(expected, expected)
            if norm != exp:
                bad.append(f"{text!r}: got {got}, want {expected}")
    lat.sort()
    total = len(CASES) * repeat
    p50 = lat[len(lat) // 2]
    p95 = lat[int(len(lat) * 0.95)]
    return BenchResult(f"tiny:{model}", (total - len(bad) - abstain) / total,
                       p50, p95, abstain, bad)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="deterministic")
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()
    if args.repeat <= 0:
        ap.error("--repeat must be positive")
    results: list[BenchResult] = []
    for name in args.models.split(","):
        name = name.strip()
        if name == "deterministic":
            results.append(run_deterministic())
        elif name == "tiny":
            from packages.dialogue_engine.tinyllm import model_id

            results.append(run_tiny(model_id(), args.repeat))
        else:
            print(f"unknown candidate {name!r}")
            return 1
    for r in results:
        print(f"== {r.name}: acc={r.accuracy:.2f} p50={r.p50_ms:.1f}ms "
              f"p95={r.p95_ms:.1f}ms abstain={r.abstain}")
        for e in r.errors[:12]:
            print(f"   miss: {e}")
    return int(any(r.errors or r.abstain for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
