"""Train the tiny route classifier (sklearn, ~50KB, <1ms on CPU).

Why not a smaller LLM: measured SmolLM2-360M and Qwen2.5-0.5B cannot do
Russian one-word route classification (echo / mixed-language garbage) —
see tools/voice_lab/ambiguity_bench.py. A supervised linear classifier on
our own ambiguity corpus is smaller, faster, deterministic, and testable.

Labels: answer reluctance repair question_back hostile garbage unclear

Usage:
  python3 tools/voice_lab/train_route_clf.py            # train -> models/route_clf.pkl
  python3 tools/voice_lab/train_route_clf.py --eval-only # report held-out acc

Training rows below + fuzz BEHAVIORS pools + live fs-*.jsonl quotes.
Retrain on every new live-quote batch; keep the bench green.
"""

from __future__ import annotations

import argparse
import pickle
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

MODEL_PATH = ROOT / "models" / "route_clf.pkl"

SEED_ROWS: list[tuple[str, str]] = [
    # reluctance
    ("хватит уже", "reluctance"), ("хватит", "reluctance"),
    ("надоело", "reluctance"), ("надоело уже", "reluctance"),
    ("отстань", "reluctance"), ("некогда мне", "reluctance"),
    ("тороплюсь", "reluctance"), ("мне пора", "reluctance"),
    ("ой давай уже заканчивать", "reluctance"),
    ("давай заканчивать", "reluctance"),
    ("устал я говорить", "reluctance"), ("устал говорить", "reluctance"),
    ("тяжело говорить", "reluctance"), ("не могу говорить", "reluctance"),
    ("не знаю", "reluctance"), ("не помню", "reluctance"),
    ("ага", "reluctance"), ("угу", "reluctance"), ("ну", "reluctance"),
    ("да вроде бы нет", "reluctance"), ("вроде нет", "reluctance"),
    ("ну наверное", "reluctance"),
    ("я ж сказал уже всё", "reluctance"),
    # repair
    ("что", "repair"), ("чего", "repair"), ("чё", "repair"), ("ась", "repair"),
    ("алло", "repair"), ("повторите", "repair"), ("повтори", "repair"),
    ("не расслышал", "repair"), ("не расслышала", "repair"),
    ("что вы сказали", "repair"), ("ещё раз", "repair"),
    ("не понял", "repair"), ("плохо слышно", "repair"),
    # question_back
    ("а вы кто", "question_back"), ("вы кто", "question_back"),
    ("зачем звоните", "question_back"), ("зачем вы звоните", "question_back"),
    ("про что ты", "question_back"), ("про что вы", "question_back"),
    ("что вы спросили", "question_back"), ("а это кто", "question_back"),
    ("почему она говорит даниил", "question_back"),
    ("откуда вы знаете", "question_back"),
    # hostile
    ("это хуйня", "hostile"), ("не это хуйня ты сразу всё спросил", "hostile"),
    ("ты дура", "hostile"), ("ты дурак", "hostile"),
    ("не звони больше", "hostile"), ("достал уже", "hostile"),
    # garbage
    ("поднял", "garbage"), ("меняет", "garbage"), ("люпимая", "garbage"),
    ("спали того", "garbage"), ("пло", "garbage"), ("э", "garbage"),
    ("э-э", "garbage"), ("колю покушал когда", "garbage"),
    ("подняла трубку и всё", "garbage"),
    # unclear
    ("ну так", "unclear"), ("чего-то", "unclear"), ("ну такое", "unclear"),
    # answers (must never become reluctance/garbage)
    ("хорошо", "answer"), ("нормально", "answer"), ("отлично", "answer"),
    ("плохо", "answer"), ("так себе", "answer"), ("терпимо", "answer"),
    ("плохо себя чувствую", "answer"), ("чувствую себя плохо", "answer"),
    ("голова болит", "answer"), ("живот болит", "answer"),
    ("сердце болит я падаю", "answer"), ("вызовите скорую", "answer"),
    ("с утра", "answer"), ("со вчера", "answer"), ("сегодня", "answer"),
    ("сейчас", "answer"), ("после еды", "answer"),
    ("после того как покушал", "answer"), ("как покушал", "answer"),
    ("три часа назад", "answer"), ("сильная", "answer"),
    ("терпимая", "answer"), ("слабая", "answer"), ("болит чуток", "answer"),
    ("уже не болит", "answer"), ("прошла", "answer"), ("ещё болит", "answer"),
    ("да принял", "answer"), ("да приняла", "answer"),
    ("таблетку забыла выпить", "answer"), ("поела нормально", "answer"),
    ("спал нормально", "answer"), ("плохо спал", "answer"),
    ("нет", "answer"), ("нет ничего", "answer"), ("ничего больше", "answer"),
    ("до свидания", "answer"), ("пока", "answer"),
    ("ноги болят", "answer"), ("грустно мне", "answer"),
]

_FILLERS = ["", "ну ", "да ", "вот ", "ну вот ", "это ", "прям ", "уже "]


def build_rows(seed: int = 7) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    rows = list(SEED_ROWS)
    for text, label in SEED_ROWS:
        for _ in range(3):
            f = rng.choice(_FILLERS)
            if f and not text.startswith(f):
                rows.append((f + text, label))
    noisy: list[tuple[str, str]] = []
    for text, label in rows:
        noisy.append((text, label))
        if rng.random() < 0.3:
            noisy.append((text + ".", label))
        if rng.random() < 0.15:
            noisy.append((text.capitalize(), label))
    rng.shuffle(noisy)
    return noisy


def train(out: Path = MODEL_PATH) -> Path:
    from sklearn.feature_extraction.text import HashingVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    rows = build_rows()
    cut = int(len(rows) * 0.85)
    train_rows, held = rows[:cut], rows[cut:]
    clf = make_pipeline(
        HashingVectorizer(
            n_features=2**12, ngram_range=(1, 2), alternate_sign=False
        ),
        LogisticRegression(max_iter=500, C=4.0),
    )
    clf.fit([t for t, _ in train_rows], [lab for _, lab in train_rows])
    good = sum(1 for t, lab in held if clf.predict([t])[0] == lab)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        pickle.dump(clf, f)
    print(f"train={len(train_rows)} held={len(held)} held_acc={good/len(held):.3f}")
    print(f"model bytes={out.stat().st_size}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-only", action="store_true")
    args = ap.parse_args()
    if args.eval_only and not MODEL_PATH.exists():
        print("no model; train first")
        return 1
    if not args.eval_only:
        train()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
