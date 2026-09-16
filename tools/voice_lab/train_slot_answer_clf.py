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

# (pending_slot, text, label). Slots: onset|duration|severity|current|wellness.
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
    # --- wellness answers (substantive self-assessment, any polarity) ---
    ("wellness", "хорошо", "answer"), ("wellness", "нормально", "answer"),
    ("wellness", "отлично", "answer"), ("wellness", "прекрасно", "answer"),
    ("wellness", "неплохо", "answer"),
    ("wellness", "хорошо себя чувствую", "answer"),
    ("wellness", "нормально себя чувствую", "answer"),
    ("wellness", "самочувствие хорошее", "answer"),
    ("wellness", "вроде нормально", "answer"),
    ("wellness", "ничего", "answer"),
    ("wellness", "плохо", "answer"), ("wellness", "мне плохо", "answer"),
    ("wellness", "мне очень плохо", "answer"),
    ("wellness", "плохое самочувствие", "answer"),
    ("wellness", "состояние не очень", "answer"),
    ("wellness", "не очень", "answer"),
    ("wellness", "болею", "answer"), ("wellness", "приболел", "answer"),
    ("wellness", "голова болит", "answer"),
    ("wellness", "более-менее", "answer"),
    ("wellness", "более менее", "answer"),
    ("wellness", "так себе", "answer"),
    ("wellness", "мне так себе", "answer"),
    ("wellness", "по состоянию мне более-менее", "answer"),
    ("wellness", "средне", "answer"), ("wellness", "терпимо", "answer"),
    ("wellness", "сойдёт", "answer"), ("wellness", "пойдёт", "answer"),
    ("wellness", "ни шатко ни валко", "answer"),
    ("wellness", "кое-как", "answer"),
    ("wellness", "помаленьку", "answer"),
    ("wellness", "ни то ни сё", "answer"),
    ("wellness", "когда как", "answer"),
    # --- wellness skips (refuse the dimension) ---
    ("wellness", "не скажу", "skip"), ("wellness", "дальше", "skip"),
    ("wellness", "давай дальше", "skip"), ("wellness", "пропусти", "skip"),
    ("wellness", "не хочу говорить", "skip"),
    # --- wellness garbage (re-ask, never close the slot) ---
    ("wellness", "абракадабра", "garbage"),
    ("wellness", "ага", "garbage"), ("wellness", "угу", "garbage"),
    ("wellness", "да", "garbage"), ("wellness", "нет", "garbage"),
    ("wellness", "алло", "garbage"), ("wellness", "э-э", "garbage"),
    ("wellness", "ну", "garbage"), ("wellness", "спасибо", "garbage"),
    ("wellness", "не знаю", "garbage"), ("wellness", "не помню", "garbage"),
    ("wellness", "даже не знаю", "garbage"),
    ("wellness", "ну не знаю", "garbage"),
    ("wellness", "не помню как", "garbage"),
    ("wellness", "хз", "garbage"),
    ("wellness", "у мужа плохо", "garbage"),
    ("wellness", "муж болеет", "garbage"),
    ("wellness", "что вы спросили", "garbage"),
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
    ("onset", "э-э.", "garbage"),
    ("severity", "э-э. э-э.", "garbage"),
    ("onset", "ну.", "garbage"),
    ("onset", "началось, когда покушал.", "garbage"),
    ("severity", "вот э-э.", "garbage"),
    ("severity", "э-э. вот", "garbage"),
    ("severity", "э-э. э-э.", "garbage"),
    ("severity", "э-э.", "garbage"),
    ("onset", "э-э.", "garbage"),
    ("severity", "э-э.", "garbage"),
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
_WELLNESS_ANSWERS = [
    "хорошо", "нормально", "отлично", "прекрасно", "неплохо",
    "плохо", "мне плохо", "очень плохо", "не очень",
    "более-менее", "более менее", "так себе", "средне", "терпимо",
    "сойдёт", "пойдёт", "ни шатко ни валко", "кое-как", "помаленьку",
    "ни то ни сё", "когда как", "болею", "приболел",
]
_WELLNESS_SKIP = [
    "дальше", "давай дальше", "пропусти", "не скажу", "не хочу говорить",
]
_WELLNESS_GARBAGE = [
    "поднял", "ага", "угу", "да", "нет", "ну", "э-э", "пло", "алло",
    "спасибо", "абракадабра", "не знаю", "не помню",
    "у мужа плохо", "муж болеет", "что вы спросили",
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
    for s in _WELLNESS_ANSWERS:
        rows.append(("wellness", s, "answer"))
    for s in _WELLNESS_SKIP:
        rows.append(("wellness", s, "skip"))
    for g in _WELLNESS_GARBAGE:
        rows.append(("wellness", g, "garbage"))
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
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline

    from tools.voice_lab.families import family_of, group_report

    rows = build_rows()
    groups = [family_of(t, s) for s, t, _ in rows]
    print(f"families: {group_report(groups)}")
    # Honest estimate: 5-fold GroupKFold by family (no variant leakage),
    # plus a learning curve (reviewer: sufficiency by curve, not by 300).
    X = [_features(s, t) for s, t, _ in rows]
    y = [lab for _, _, lab in rows]
    base = make_pipeline(
        HashingVectorizer(n_features=2**12, ngram_range=(1, 2), alternate_sign=False),
        LogisticRegression(max_iter=500, C=4.0),
    )
    import numpy as np

    gkf = GroupKFold(n_splits=5)
    fold_acc: list[float] = []
    for train_idx, test_idx in gkf.split(X, y, groups):
        clf = _clone(base)
        clf.fit([X[i] for i in train_idx], [y[i] for i in train_idx])
        pred = clf.predict([X[i] for i in test_idx])
        fold_acc.append(float(np.mean([p == y[i] for p, i in zip(pred, test_idx)])))
    print(f"group5fold: {[round(a, 3) for a in fold_acc]} mean={float(np.mean(fold_acc)):.3f}")
    for frac in (0.2, 0.4, 0.6, 0.8, 1.0):
        accs: list[float] = []
        for train_idx, test_idx in gkf.split(X, y, groups):
            cut = max(1, int(len(train_idx) * frac))
            clf = _clone(base)
            clf.fit([X[i] for i in train_idx[:cut]], [y[i] for i in train_idx[:cut]])
            pred = clf.predict([X[i] for i in test_idx])
            accs.append(float(np.mean([p == y[i] for p, i in zip(pred, test_idx)])))
        print(f"  curve@{frac:.1f}: {float(np.mean(accs)):.3f}")
    clf = base
    clf.fit(X, y)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        pickle.dump(clf, f)
    print(f"train={len(rows)} model bytes={out.stat().st_size}")
    return out


def _clone(pipe):  # sklearn Clone without importing clone at top
    from sklearn.base import clone

    return clone(pipe)


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
