"""Russian pronunciation overrides for Silero TTS (Stage C v1).

Silero v5 accepts manual stress with ``+`` immediately before the stressed
vowel. Automatic ``put_accent`` / ``put_stress_homo`` help, but homographs,
the brand «Имвера», and elderly-care vocabulary still need explicit fixes.

This module is dependency-free (regex only) and runs before SSML shaping.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Longest keys first — applied in order via sorted patterns.
_WORD_STRESS: dict[str, str] = {
    # Brand / persona (most common misreads on phone).
    "имвера": "+Имвера",
    "вера": "В+ера",
    # Care-call vocabulary (stress_tricky corpus + live pools).
    "позвонит": "позвон+ит",
    "позвоните": "позвон+ите",
    "позвонили": "позвон+или",
    "звонит": "звон+ит",
    "звоните": "звон+ите",
    "звонок": "звон+ок",
    "звонка": "звонк+а",
    "договор": "догов+ор",
    "договора": "догов+ора",
    "каталоге": "катал+оге",
    "каталог": "катал+ог",
    "лекарство": "лек+арство",
    "лекарства": "лек+арства",
    "кашель": "к+ашель",
    "щавель": "щав+ель",
    "торты": "т+орты",
    "торт": "т+орт",
    "банты": "б+анты",
    "краны": "кр+аны",
    "кран": "кр+ан",
    "остановке": "остан+овке",
    "остановка": "остан+овка",
    "прихожей": "прих+ожей",
    "справочную": "справ+очную",
    "справочная": "справ+очная",
    "таблетки": "табл+етки",
    "таблетку": "табл+етку",
    "таблетка": "табл+етка",
    "красивее": "крас+ивее",
    "полезное": "пол+езное",
    "полезный": "пол+езный",
    "очки": "+очки",
    "сердце": "с+ердце",
    "хлебнице": "хлебн+ице",
    "хлебница": "хлебн+ица",
    "поликлинике": "поликлин+ике",
    "поликлиника": "поликлин+ика",
    "поликлиники": "поликлин+ики",
    "диспансер": "диспанс+ер",
    "диагноз": "диагн+оз",
    "анализ": "анал+из",
    "анализа": "анал+иза",
    "рецепт": "рец+епт",
    "терапевт": "терап+евт",
    "профилактика": "профил+актика",
    "витамины": "витам+ины",
    "больница": "больн+ица",
    "больнице": "больн+ице",
    "аптека": "апт+ека",
    "аптеке": "апт+еке",
    "регистратура": "регистрат+ура",
    "регистратуре": "регистрат+уре",
    "самочувствие": "самоч+увствие",
    "самочувствия": "самоч+увствия",
    "головокружение": "головокруж+ение",
    "давление": "давл+ение",
    "давления": "давл+ения",
    "свитер": "св+итер",
    "компот": "комп+от",
    "сухофруктов": "сухофр+уктов",
    "обогреватель": "обогрев+атель",
    "диспансеризацию": "диспансериз+ацию",
    "диспансеризация": "диспансериз+ация",
}

_PHRASE_STRESS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bиз\s+имвера\b", re.IGNORECASE),
        "из +Имвера",
    ),
    (
        re.compile(r"\bиз\s+сервиса\s+имвера\b", re.IGNORECASE),
        "из сервиса +Имвера",
    ),
    (
        re.compile(r"\bэто\s+вера\s+из\b", re.IGNORECASE),
        "это В+ера из",
    ),
    (
        re.compile(r"\bна\s+связи\s+вера\b", re.IGNORECASE),
        "на связи В+ера",
    ),
)

_LATIN_BRAND_RE = re.compile(r"\bIMVERA\b", re.IGNORECASE)
_LATIN_BRAND_REPL = "+Имвера"

_COMPILED_WORDS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (
        re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE),
        stressed,
    )
    for word, stressed in sorted(_WORD_STRESS.items(), key=lambda kv: -len(kv[0]))
)


@dataclass
class PronunciationOverride:
    kind: str
    source: str
    replacement: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "source": self.source,
            "replacement": self.replacement,
        }


@dataclass
class PronunciationTrace:
    original: str
    normalized: str
    overrides: list[PronunciationOverride] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "TTS_INPUT_ORIGINAL": self.original,
            "TTS_INPUT_NORMALIZED": self.normalized,
            "PRONUNCIATION_OVERRIDES": [o.to_dict() for o in self.overrides],
        }

    def format_lines(self) -> str:
        lines = [
            f'TTS_INPUT_ORIGINAL: "{self.original}"',
            f'TTS_INPUT_NORMALIZED: "{self.normalized}"',
            f"PRONUNCIATION_OVERRIDES: {[o.to_dict() for o in self.overrides]}",
        ]
        return "\n".join(lines)


def _sub_with_trace(
    text: str,
    pattern: re.Pattern[str],
    repl: str,
    *,
    kind: str,
    overrides: list[PronunciationOverride],
) -> str:
    def _replacer(match: re.Match[str]) -> str:
        overrides.append(
            PronunciationOverride(
                kind=kind,
                source=match.group(0),
                replacement=repl,
            )
        )
        return repl

    return pattern.sub(_replacer, text)


def apply_pronunciation_with_trace(text: str) -> PronunciationTrace:
    """Apply overrides and record every substitution for TTS debugging."""
    if not text or not text.strip():
        return PronunciationTrace(original=text, normalized=text)

    overrides: list[PronunciationOverride] = []
    out = text

    for match in _LATIN_BRAND_RE.finditer(text):
        overrides.append(
            PronunciationOverride(
                kind="latin_brand",
                source=match.group(0),
                replacement=_LATIN_BRAND_REPL,
            )
        )
    out = _LATIN_BRAND_RE.sub(_LATIN_BRAND_REPL, out)

    for pattern, repl in _PHRASE_STRESS:
        out = _sub_with_trace(out, pattern, repl, kind="phrase", overrides=overrides)

    for pattern, repl in _COMPILED_WORDS:
        out = _sub_with_trace(out, pattern, repl, kind="word", overrides=overrides)

    return PronunciationTrace(original=text, normalized=out, overrides=overrides)


def apply_pronunciation(text: str) -> str:
    """Apply brand + domain stress overrides for Silero synthesis."""
    return apply_pronunciation_with_trace(text).normalized


def prepare_tts_text(text: str) -> str:
    """Full spoken-text prep before TN/SSML (pronunciation first)."""
    return apply_pronunciation(text)
