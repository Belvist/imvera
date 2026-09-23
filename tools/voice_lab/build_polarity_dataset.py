"""Build polarity v1 dataset deterministically from tracked sources.

Regenerates datasets/semantic_nlu/polarity_v1.jsonl (gitignored artifact):
- live elderly utterances (docs/live-calls.md, User lines),
- corpus user texts (generate_corpus, code),
- rule pre-label + bulk patterns + expert exception tables (below).

Every labeling decision is in this file. No /tmp inputs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

EXCLUDE = re.compile(
    r"^(привет|здравствуйте|добрый|алло|да\??|нет\??|а\??|ага|угу|спасибо|"
    r"до свидания|пока|ка\?*)\.?$"
    r"|^(а\s+)?погода|кто\s+вы|что\s+вы|повтори|алло"
    r"|\?$",
    re.I,
)
TEMPORAL_ONLY = re.compile(
    r"^((вчера|сегодня|позавчера|утром|вечером|ночью|сейчас|давно|недавно|с\s+утра|в\s+\d|вчерашнего\s+дня)[\s,.\d:]*)+$",
    re.I,
)
HEDGE = re.compile(
    r"(вроде|более[\s\-—]*менее|так\s+себе|средн\w*|терпимо|ну\s+такое|сойд[её]т)",
    re.I,
)
POS_WORD = re.compile(
    r"(хорошо|нормально|отлично|прекрасно|неплохо|замечательно|супер)", re.I
)
NEG_WORD = re.compile(
    r"(плох|бол(?!ее(?:\b|-))|тошн|кружи|дурно|мутит|тяжел|температур|давлен|болит|ноет|"
    r"ломит|давит|тошнит|знобит|озноб|беспокоит|тревожит|мешает|кружит|слаб|устал|"
    r"отвратительн|паршив|хреново|фигово|дерьмово|гнусно|мерзко|погано|кошмарно|"
    r"не\s+очень|не\s+важно|слабость)",
    re.I,
)
NEGATED_POS = re.compile(r"\bне\s+(хорошо|нормально|отлично|прекрасно)\b", re.I)
RESOLVED = re.compile(
    r"(прошл[аои]|отпустило|нет\s+боли|боли\s+нет|отсутствует|кончилось)", re.I
)
POS_WORD = re.compile(
    r"(хорошо|нормально|отлично|прекрасно|неплохо|замечательно|супер)", re.I
)
NEG_WORD = re.compile(
    r"(плох|бол(?!ее(?:\b|-))|тошн|кружи|дурно|мутит|тяжел|температур|давлен|болит|ноет|"
    r"ломит|давит|тошнит|знобит|озноб|беспокоит|тревожит|мешает|кружит|слаб|устал|"
    r"отвратительн|паршив|хреново|фигово|дерьмово|гнусно|мерзко|погано|кошмарно|"
    r"не\s+очень|не\s+важно|слабость)",
    re.I,
)
NEGATED_POS = re.compile(r"\bне\s+(хорошо|нормально|отлично|прекрасно)\b", re.I)
RESOLVED = re.compile(
    r"(прошл[аои]|отпустило|нет\s+боли|боли\s+нет|отсутствует|кончилось)", re.I
)

# Bulk expert tables (second pass over REVIEW leftovers).
UNCERTAIN_PATTERNS = [
    r"пойд[её]т",
    r"не\s+идеально",
    r"не\s+выспался",
    r"^не\s+знаю",
    r"не\s+могу\s+сказать",
    r"не\s+понимаю",
    r"^нет[,\s]",
    r"ничего\s+неважно",
    r"забыл",
    r"не\s+удалось",
    r"не\s+успел",
    r"не\s+приняла",
    r"не\s+начено",
    r"непонятно",
    r"блядь",
    r"отстань",
    r"а-а,\s+не\s+знаю",
    r"ой,\s+привет\.\s+не\s+знаю",
    r"привет\.\s+не\s+знаю",
    r"привет\.\s+чувствую\s+себя.*не\s+знаю",
    r"понятно\s+пока",
    r"разде\s+говорил\s+живот",
    r"я\s+ж\s+сказал\s+уже\s+всё",
]
POSITIVE_PATTERNS = [
    r"могу\s+справиться",
    r"покушал\s+и\s+попил",
    r"всё\s+хорошо\s+у\s+меня",
    r"спало\s+великолепно",
    r"стало\s+лучше",
    r"чувствую\s+себя\s+великолепно",
]
NEGATIVE_PATTERNS = [
    r"умираю",
    r"сердце\s+умирало",
    r"хорошо…\s+хотя\s+нет,\s+плохо",
    r"ху[её]вое.*настроение",
    r"вырвало\s+меня",
    r"продолжается\s+уже\s+пятый\s+час",
    r"живот\s+пучит",
    r"я\s+сейчас\s+умру",
]
EXCLUDE_PATTERNS = [
    r"пимба",
    r"сидеть\s+дома",
    r"в\s+течение\s+часа",
    r"давность|давно\s+началось|достаточно\s+давно",
    r"началось",
    r"наверное,\s+(раннее|только)",
    r"принял|удалось|это\s+я\b",
    r"каждый\s+день|не\s+каждый",
    r"на\s+восемь|на\s+сегодня\s+нету",
    r"лекарств|таблетки|выпил",
    r"дома\s+посижу|планов?\s+нет",
    r"макароны\s+поел",
    r"ну,\s+сильная",
    r"не\s+спросишь",
    r"продолжительное\s+время",
    r"с\s+10:00",
    r"самого\s+утра",
    r"сходить\s+в\s+магазин",
    r"тут\s+по\s+факту",
    r"уже\s+с\s+четырёх",
    r"четыре\s+часа",
    r"это\s+не\s+назначено",
    r"всего\s+доброго",
    r"со\s+мной\s+замуж",
    r"спали\s+того",
    r"в\s+магазин\s+сейчас\s+пойду",
    r"у\s+кого\s+поглушил",
    r"планов\s+никаких\s+нету",
    r"магнитной\s+бури",
    r"^ммм$",
]
# Live failure shapes that must stay positive (fs-27a3ced4 / 2257cab2 class).
LIVE_POSITIVE = [
    "Привет. Всё хорошо.",
    "Привет. Всё хорошо. Только что покушала.",
    "Здравствуйте, нормально.",
    "Здравствуйте. Самочувствие хорошее.",
    "Добрый день. Всё отлично.",
    "Привет. Нормально себя чувствую.",
    "Ой, привет. Хорошо.",
    "Да, всё хорошо.",
    "Ничего меня не беспокоит.",
    "Ничего не беспокоит.",
    "Ничего не болит.",
    "Жалоб нет.",
    "Нет жалоб.",
    "Всё спокойно.",
    "Нет, ничего не болит.",
    "Голова не болит.",
    "Давление не беспокоит.",
    "Ничего не тревожит.",
    "Всё прошло, ничего не болит.",
    "Живот не болит.",
    "Нет, всё спокойно, ничего не беспокоит.",
    "Сердце не болит.",
    "Умираю.",
    "Помогите.",
]


def prelabel(text: str) -> str | None:
    low = text.lower()
    if EXCLUDE.search(low) or TEMPORAL_ONLY.match(low):
        return None
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, low):
            return None
    for pat in NEGATIVE_PATTERNS:
        if re.search(pat, low):
            return "negative"
    for pat in POSITIVE_PATTERNS:
        if re.search(pat, low):
            return "positive"
    # Valence words beat hedge tables («Не знаю, вот фильм посмотрел и сразу
    # плохо стало» is negative, not uncertain; «нормально, но болит» too).
    has_neg = bool(NEG_WORD.search(low))
    has_pos = bool(POS_WORD.search(low)) and not NEGATED_POS.search(low)
    if RESOLVED.search(low) and not has_neg:
        return "positive"
    if has_neg and not has_pos:
        return "negative"
    if has_pos and not has_neg:
        return "positive"
    for pat in UNCERTAIN_PATTERNS:
        if re.search(pat, low):
            return "uncertain"
    if HEDGE.search(low):
        return "uncertain"
    return "REVIEW"


def collect_texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    live = ROOT / "docs" / "live-calls.md"
    if live.is_file():
        for m in re.finditer(r"^- User\[[^\]]+\]: (.+)$", live.read_text(), flags=re.M):
            t = m.group(1).strip()
            if 2 <= len(t.split()) <= 12:
                texts[t] = "live"
    from packages.dialogue_engine.corpus.generator import generate_corpus
    from packages.dialogue_engine.corpus.schema import UserStep

    for s in generate_corpus():
        for step in s.steps:
            if isinstance(step, UserStep) and step.text:
                t = step.text.strip()
                if t:
                    texts.setdefault(t, "corpus")
    return texts


def main() -> None:
    from packages.dialogue_engine.fast_interpreter import (
        _WELLNESS_NEGATIVE,
        _detect_polarity,
    )

    texts = collect_texts()
    rows: list[dict] = []
    review: list[str] = []
    for text in sorted(texts):
        low = text.lower()
        label: str | None = None
        source = "bulk"
        if _WELLNESS_NEGATIVE.search(low):
            label, source = "negative", "rule-neg"
        elif _detect_polarity(text) in ("positive", "negative"):
            label, source = _detect_polarity(text), "rule-pol"
        else:
            v = prelabel(text)
            if v is None:
                continue
            if v == "REVIEW":
                review.append(text)
                continue
            label, source = v, "expert-bulk"
        rows.append({"text": text, "label": label, "source": source})
    for text in LIVE_POSITIVE:
        if text not in {r["text"] for r in rows}:
            rows.append(
                {
                    "text": text,
                    "label": (
                        "negative" if text in ("Умираю.", "Помогите.") else "positive"
                    ),
                    "source": "expert-live-shapes",
                }
            )
    if review:
        print(f"UNRESOLVED REVIEW: {len(review)}")
        for t in review[:40]:
            print("  ", repr(t))
        raise SystemExit(1)
    out = ROOT / "datasets" / "semantic_nlu" / "polarity_v1.jsonl"
    out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8"
    )
    import collections

    print(collections.Counter(r["label"] for r in rows), len(rows))


if __name__ == "__main__":
    main()
