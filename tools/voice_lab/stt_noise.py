"""STT degradation layer — stress like the phone hears, not like text reads.

Live traces prove the failure mode is EARS, not brain: «Очи болит» (голова),
«Триво» (тревожно), «Наз болит» (нос?), «Пло.» (плохо), «Спали того»,
«Колю покушал когда?». Clean-text stress never sees these.

Transforms (seeded, calibrated to live pairs):
  truncate   «Плохо.» → «Пло.» / «Здравствуйте» → «Здра.»
  voice      о↔а, и↔ы, г↔к, д↔т, б↔п, в↔ф, з↔с, ж↔ш, е↔и (unstressed slur)
  consonant  хто↔кто, л↔н, р↔л, м↔н (nasal swaps)
  endings    drop/swap inflection («головная» → «головно», «болит» → «балит»)
  merge      «не знаю» → «незнаю»; split «потому» → «по тому»
  filler     prepend/append «ну », «э-э», «вот », «да »
  digits     «восемь» → «8», «8:00» → «восемь» (STT normalizer flips)

Usage:
  degrade("Голова болит.", rng, p=0.35) -> "Голово балит."
  stress: scripts/dialogue_stress_soak.py --stt-noise 0.35
"""

from __future__ import annotations

import random
import re

_VOICE = str.maketrans({
    "о": "а", "а": "о", "и": "ы", "е": "и",
    "г": "к", "д": "т", "б": "п", "в": "ф", "з": "с", "ж": "ш",
})
_NASAL = [("хто", "кто"), ("кто", "хто"), ("л", "н"), ("р", "л"), ("м", "н")]

_NUM2WORD = {
    "8": "восемь", "6": "шесть", "3": "три", "4": "четыре", "5": "пять",
    "7": "семь", "9": "девять", "10": "десять", "2": "два",
}
_WORD2NUM = {v: k for k, v in _NUM2WORD.items()}


def _truncate(text: str, rng: random.Random) -> str:
    words = text.split()
    if not words:
        return text
    i = rng.randrange(len(words))
    w = words[i].rstrip(".!?")
    if len(w) > 4:
        words[i] = w[: rng.randint(2, len(w) - 2)] + "."
    return " ".join(words)


def _slur(text: str, rng: random.Random) -> str:
    chars = list(text.lower())
    hits = [i for i, c in enumerate(chars) if c in "оаиегдбвзж"]
    if not hits:
        return text
    for i in rng.sample(hits, k=min(len(hits), rng.randint(1, 2))):
        chars[i] = _VOICE.get(chars[i], chars[i])
    out = "".join(chars)
    return out[:1].upper() + out[1:] if text[:1].isupper() else out


def _nasal(text: str, rng: random.Random) -> str:
    low = text.lower()
    for a, b in _NASAL:
        if a in low and rng.random() < 0.5:
            low = low.replace(a, b, 1)
            break
    return low.capitalize() if text[:1].isupper() else low


def _endings(text: str, rng: random.Random) -> str:
    def fix(m: re.Match) -> str:
        w = m.group(0)
        return w[:-2] + rng.choice(["о", "а", "е", ""]) if len(w) > 5 else w

    return re.sub(r"[а-яё]{6,}", fix, text.lower(), count=1)


def _digits(text: str, rng: random.Random) -> str:
    for d, w in _NUM2WORD.items():
        if d in text and rng.random() < 0.7:
            return text.replace(d, w, 1)
    for w, d in _WORD2NUM.items():
        if w in text.lower() and rng.random() < 0.4:
            return re.sub(w, d, text, count=1, flags=re.I)
    return text


def _filler(text: str, rng: random.Random) -> str:
    f = rng.choice(["Ну ", "Э-э. ", "Вот ", "Да "])
    return f + text if rng.random() < 0.5 else text + " " + f.strip()


def degrade(text: str, rng: random.Random, p: float = 0.35) -> str:
    """Apply 1-2 seeded STT degradations with probability p per turn."""
    if rng.random() > p:
        return text
    fns = [_truncate, _slur, _nasal, _endings, _digits, _filler]
    for fn in rng.sample(fns, k=rng.randint(1, 2)):
        try:
            text = fn(text, rng)
        except Exception:
            pass
    return text
