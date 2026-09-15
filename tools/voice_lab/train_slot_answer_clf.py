"""Train the slot-answer classifier (sklearn, ~200KB, <1ms on CPU).

Problem it solves (no more phrase patching): the user cannot enumerate how
an elder answers «когда началось?» / «сильная?» — anchors will always miss
the next paraphrase («жить можно», «раньше началось это», ...). Instead of
extending word lists per incident, this model learns the BOUNDARY between
answer / skip / garbage for a pending slot from pools + live quotes.

Labels: answer | skip | garbage
  answer  — dates/grades the pending slot (record raw, capped) or clearly
            tries to (forward progress, no re-ask)
  skip    — refuses the dimension («дальше», «не помню когда», «нет» to onset)
            → skip markers, advance, never re-ask, never fabricate
  garbage — STT debris / vent / off-topic → existing clarify/divert path

Consulted ONLY when lexical anchors miss (second tier), validator-clamped,
probability threshold 0.6, fail-open to garbage path. Never writes invented
values: answer records the user's own words.

Usage:
  python3 tools/voice_lab/train_slot_answer_clf.py
  python3 tools/voice_lab/train_slot_answer_clf.py --eval-only

LOOP (this is the anti-patch process): every live quote the anchors missed
goes to LIVE_QUOTES below with its true label → retrain (1 min) → bench +
fuzz must stay green. No regex edits for paraphrases anymore.
"""

from __future__ import annotations

import argparse
import pickle
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

MODEL_PATH = ROOT / "models" / "slot_answer_clf.pkl"

# (pending_slot, text, label). Slots: onset|duration|severity|current.
SEED_ROWS: list[tuple[str, str, str]] = [
    # --- temporal answers (any slot onset/duration) ---
    ("onset", "с утра", "answer"), ("onset", "со вчера", "answer"),
    ("onset", "вчера", "answer"), ("onset", "сегодня", "answer"),
    ("onset", "сейчас", "answer"), ("onset", "давно", "answer"),
    ("onset", "раньше началось это", "answer"),
    ("onset", "раньше", "answer"), ("onset", "три часа назад", "answer"),
    ("onset", "после еды", "answer"), ("onset", "как покушал", "answer"),
    ("onset", "после того как покушал", "answer"),
    ("onset", "на восемь", "answer"), ("onset", "вчера в восемь", "answer"),
    ("onset", "в восемь вечера", "answer"), ("onset", "утром макароны поел", "answer"),
    ("onset", "когда утром макароны поел", "answer"),
    ("onset", "уже неделю", "answer"), ("onset", "второй день", "answer"),
    ("onset", "только что", "answer"), ("onset", "буквально час назад", "answer"),
    ("onset", "с обеда", "answer"), ("onset", "ночью началось", "answer"),
    ("duration", "с утра", "answer"), ("duration", "три часа назад", "answer"),
    ("duration", "раньше", "answer"), ("duration", "после еды", "answer"),
    # --- severity answers ---
    ("severity", "сильная", "answer"), ("severity", "терпимая", "answer"),
    ("severity", "терпимо", "answer"), ("severity", "слабая", "answer"),
    ("severity", "пойдёт", "answer"), ("severity", "пойдет", "answer"),
    ("severity", "сойдёт", "answer"), ("severity", "жить можно", "answer"),
    ("severity", "более-менее", "answer"), ("severity", "так себе", "answer"),
    ("severity", "болит чуток", "answer"), ("severity", "невыносимо", "answer"),
    ("severity", "очень сильно", "answer"),
    # --- current answers ---
    ("current", "ещё болит", "answer"), ("current", "уже не болит", "answer"),
    ("current", "прошла", "answer"), ("current", "полегче", "answer"),
    ("current", "болит чуток", "answer"),
    # --- skips (refuse the dimension, move on) ---
    ("onset", "дальше", "skip"), ("onset", "давай дальше", "skip"),
    ("onset", "пропусти", "skip"), ("onset", "не помню когда", "skip"),
    ("onset", "неважно", "skip"), ("onset", "не знаю", "skip"),
    ("onset", "нет", "skip"), ("onset", "не скажу", "skip"),
    ("duration", "дальше", "skip"), ("duration", "не помню", "skip"),
    ("severity", "не знаю", "skip"), ("severity", "не скажу", "skip"),
    ("severity", "вроде нет", "skip"),
    # --- garbage (debris / vent / off-topic for the slot) ---
    ("onset", "поднял", "garbage"), ("onset", "пло", "garbage"),
    ("onset", "э-э", "garbage"), ("onset", "спасибо", "garbage"),
    ("onset", "колю покушал когда", "garbage"),
    ("onset", "началось когда покушал", "garbage"),
    ("onset", "ага", "garbage"), ("onset", "ну", "garbage"),
    ("onset", "это хуйня", "garbage"), ("onset", "алло", "garbage"),
    ("onset", "спали того", "garbage"),
    ("severity", "поднял", "garbage"), ("severity", "ага", "garbage"),
    ("severity", "ну такое", "garbage"), ("severity", "э-э", "garbage"),
    ("duration", "ага", "garbage"), ("duration", "поднял", "garbage"),
    # --- LIVE_QUOTES: append every anchor-miss with its true label ---
    ("onset", "когда с работы пришла", "answer"),
    ("onset", "раньше началось это", "answer"),
    ("onset", "началось это буквально три часа назад", "answer"),
    ("severity", "жить можно", "answer"),
]

_FILLERS = ["", "ну ", "вот ", "прям ", "это "]

# Systematic preload families (generated — no live data needed).
# Open paraphrases still go to LIVE_QUOTES only, never to regex.
_NUM_WORDS = [
    "час", "два", "три", "четыре", "пять", "шесть", "семь", "восемь",
    "девять", "десять", "одиннадцать", "двенадцать",
]
_WEEKDAYS = [
    "понедельник", "вторник", "среду", "четверг", "пятницу", "субботу",
    "воскресенье",
]
_SEV_ANSWERS = [
    "жить можно", "более-менее", "более менее", "сойдёт", "сойдет",
    "пойдёт", "пойдет", "терпимо", "терпимая", "нормально", "так себе",
    "средне", "слабая", "сильная", "очень сильная", "невыносимо",
    "болит чуток", "чуть-чуть", "не очень", "побаливает",
]
_SKIP_FORMS = [
    "дальше", "давай дальше", "пропусти", "не помню когда", "не помню",
    "не знаю", "неважно", "не важно", "нет", "не скажу",
]
_GARBAGE_FORMS = [
    "поднял", "ага", "угу", "ну", "э-э", "пло", "алло", "спасибо",
    "колю покушал когда", "это хуйня", "чего-то там",
]


def _preload() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for slot in ("onset", "duration"):
        for n in _NUM_WORDS:
            rows.append((slot, f"в {n}", "answer"))
            rows.append((slot, f"в {n} часов", "answer"))
        for d in _WEEKDAYS:
            rows.append((slot, f"в {d}", "answer"))
            rows.append((slot, f"с {d}", "answer"))
        for t in ("с утра", "со вчера", "вчера", "сегодня", "сейчас",
                  "давно", "раньше", "только что", "ночью", "вечером"):
            rows.append((slot, t, "answer"))
            rows.append((slot, f"началось {t}", "answer"))
        for s in _SKIP_FORMS:
            rows.append((slot, s, "skip"))
        for g in _GARBAGE_FORMS:
            rows.append((slot, g, "garbage"))
    for s in _SEV_ANSWERS:
        rows.append(("severity", s, "answer"))
    for s in _SKIP_FORMS:
        rows.append(("severity", s, "skip"))
    for g in _GARBAGE_FORMS:
        rows.append(("severity", g, "garbage"))
    for c in ("ещё болит", "уже не болит", "прошла", "полегче", "болит"):
        rows.append(("current", c, "answer"))
    return rows


def build_rows(seed: int = 11) -> list[tuple[str, str, str]]:
    rng = random.Random(seed)
    rows = list(SEED_ROWS) + _preload()
    for slot, text, label in SEED_ROWS:
        for _ in range(2):
            f = rng.choice(_FILLERS)
            if f and not text.startswith(f):
                rows.append((slot, f + text, label))
    rng.shuffle(rows)
    return rows


def _features(slot: str, text: str) -> str:
    return f"{slot} || {text.strip().lower()}"


def train(out: Path = MODEL_PATH) -> Path:
    from sklearn.feature_extraction.text import HashingVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    rows = build_rows()
    cut = int(len(rows) * 0.85)
    train_rows, held = rows[:cut], rows[cut:]
    clf = make_pipeline(
        HashingVectorizer(n_features=2**12, ngram_range=(1, 2), alternate_sign=False),
        LogisticRegression(max_iter=500, C=4.0),
    )
    clf.fit([_features(s, t) for s, t, _ in train_rows],
            [lab for _, _, lab in train_rows])
    good = sum(1 for s, t, lab in held if clf.predict([_features(s, t)])[0] == lab)
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
