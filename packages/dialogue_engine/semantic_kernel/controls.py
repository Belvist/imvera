"""Canonical control contract — single enum across Kernel and DialogueEngine."""

from __future__ import annotations

import re
from dataclasses import dataclass

CANONICAL_CONTROLS = frozenset(
    {
        "none",
        "stop_call",
        "revoke_consent",
        "defer",
        "wrong_person",
        "pause",
    }
)

# Exact phrase → (dialogue_act, control). yes/no/repeat/unknown are NOT controls.
_REPAIR_PREFIXES: tuple[str, ...] = (
    "алло",
    "повторите",
    "повтори",
    "ещё раз",
    "еще раз",
    "не понял",
    "не поняла",
    "не расслышал",
    "не расслышала",
    "что вы сказали",
    "слышите",
    "слышишь",
    "ты меня",
    "вы меня",
    "что?",
    "что",
)

_LEVEL0_EXACT: dict[str, tuple[str, str]] = {
    "угу": ("backchannel", "none"),
    "ага": ("backchannel", "none"),
    "мм": ("backchannel", "none"),
    "ммм": ("backchannel", "none"),
    "стоп": ("answer", "stop_call"),
    "хватит": ("answer", "stop_call"),
    "остановите": ("answer", "stop_call"),
    "до свидания": ("answer", "stop_call"),
    "всего доброго": ("answer", "stop_call"),
    "пока": ("answer", "stop_call"),
    "заканчиваем": ("answer", "stop_call"),
    "закончим": ("answer", "stop_call"),
    "закончим разговор": ("answer", "stop_call"),
    "давайте закончим": ("answer", "stop_call"),
    "хватит разговор": ("answer", "stop_call"),
    "подождите": ("answer", "pause"),
    "подожди": ("answer", "pause"),
    "минуточку": ("answer", "pause"),
    "секундочку": ("answer", "pause"),
    "погодите": ("answer", "pause"),
    "позже": ("answer", "defer"),
    "не хочу разговаривать": ("answer", "revoke_consent"),
    "не хочу": ("answer", "revoke_consent"),
    "не звоните": ("answer", "stop_call"),
    "больше не звоните": ("answer", "stop_call"),
    "не надо звонить": ("answer", "stop_call"),
    "не беспокойте": ("answer", "stop_call"),
    "не беспокоить": ("answer", "stop_call"),
    "не ваш человек": ("answer", "wrong_person"),
    "не тот номер": ("answer", "wrong_person"),
}


@dataclass(frozen=True)
class Level0Match:
    dialogue_act: str
    control: str


def match_repair(text: str) -> Level0Match | None:
    norm = text.strip().lower()
    if not norm:
        return None
    if re.match(r"^(что|чего|чё|ась)\??$", norm):
        return Level0Match(dialogue_act="repair", control="none")
    # «О чём ты говоришь?» / «чего ты сказала?» — didn't hear, needs a
    # repeat of Vera's last question (live: user explicitly asked for this).
    if re.search(
        r"(о\s+ч[её]м\s+ты\s+(говоришь|говорите|сказала|толкуешь)|"
        r"чего\s+ты\s+(сказала|говоришь)|"
        r"что\s+ты\s+(сказала|говоришь)|"
        r"не\s+услышал[а]?)",
        norm,
    ):
        return Level0Match(dialogue_act="repair", control="none")
    for prefix in sorted(_REPAIR_PREFIXES, key=len, reverse=True):
        if norm == prefix or norm.startswith(prefix + " ") or norm.startswith(prefix + ","):
            return Level0Match(dialogue_act="repair", control="none")
    if re.search(r"(слыш\w*|повтор\w*)", norm):
        return Level0Match(dialogue_act="repair", control="none")
    return None


def match_level0(text: str) -> Level0Match | None:
    repair = match_repair(text)
    if repair is not None:
        return repair
    norm = text.strip().lower().rstrip(".!?…")
    if not norm:
        return None
    # Topic-level refusal («(я) не хочу про таблетки говорить», slurred or
    # not) is NOT consent revoke — the dialogue drops the topic (spec 9).
    # Only call-level refusal reaches control. Unanchored: STT inserts
    # leading words («я») and slurs vowels, anchors miss them.
    if re.search(
        r"не\s+(хоч[уы]|буд[уы])\b.{0,12}\b(про|об|это|таблет|лекар|говорить|обсуждать|рассказ)",
        norm,
    ):
        return None
    if re.match(r"^не хочу\s+(про|об)\b", norm) or re.match(
        r"^не\s+(буду|хочу)\s+(это\s+)?обсуждать\b", norm
    ):
        return None
    for phrase, (act, control) in sorted(_LEVEL0_EXACT.items(), key=lambda x: -len(x[0])):
        if norm == phrase or norm.startswith(phrase + " "):
            return Level0Match(dialogue_act=act, control=control)
    return None


def normalize_control(value: str) -> str:
    if value in CANONICAL_CONTROLS:
        return value
    legacy = {
        "stop": "stop_call",
        "refuse": "revoke_consent",
        "yes": "none",
        "no": "none",
        "unknown": "none",
        "repeat": "none",
        "backchannel": "none",
    }
    return legacy.get(value, "none")
