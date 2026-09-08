"""Topic-based dialogue — active issue, pending queue, dimension tracking.

Ports the adaptive-layer *ideas* from imvera_voice_mvp without regex soup:
detect families from user text, track what is already known, ask only missing
dimensions, suspend/resume topics. Background slots (wellness/mood/sleep/plans)
are filled when a topic is sufficiently covered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState


class TopicFamily(StrEnum):
    SLEEP = "sleep"
    ABDOMINAL_PAIN = "abdominal_pain"
    HEADACHE = "headache"
    LIMB_PAIN = "limb_pain"
    MOOD = "mood_loneliness"
    MEDICATION = "medication"
    GENERAL_SYMPTOM = "general_symptom"


# Ordered dimensions per family — first uncovered dimension wins.
TOPIC_PLANS: dict[str, tuple[str, ...]] = {
    TopicFamily.SLEEP: ("pattern", "daytime_impact"),
    TopicFamily.ABDOMINAL_PAIN: ("current", "onset"),
    TopicFamily.HEADACHE: ("onset", "severity"),
    TopicFamily.LIMB_PAIN: ("onset", "function"),
    TopicFamily.MOOD: ("intensity", "social"),
    TopicFamily.MEDICATION: ("status_today",),
    TopicFamily.GENERAL_SYMPTOM: ("concern", "duration"),
}

# Background daily-check slot filled when topic completes.
TOPIC_TO_SLOT: dict[str, str] = {
    TopicFamily.SLEEP: "sleep",
    TopicFamily.MOOD: "mood",
    TopicFamily.MEDICATION: "plans",
    TopicFamily.HEADACHE: "wellness",
    TopicFamily.ABDOMINAL_PAIN: "wellness",
    TopicFamily.LIMB_PAIN: "wellness",
    TopicFamily.GENERAL_SYMPTOM: "wellness",
}

_TOPIC_PRIORITY: tuple[str, ...] = (
    TopicFamily.HEADACHE,
    TopicFamily.ABDOMINAL_PAIN,
    TopicFamily.LIMB_PAIN,
    TopicFamily.SLEEP,
    TopicFamily.MOOD,
    TopicFamily.MEDICATION,
    TopicFamily.GENERAL_SYMPTOM,
)

_SLEEP_MARKERS = (
    "плохо спал",
    "плохо спала",
    "не высп",
    "не спал",
    "не спала",
    "бессон",
    "сон плох",
    "проснул",
    "проснула",
    "не мог заснуть",
    "не могла заснуть",
)
_ABDOMINAL_MARKERS = ("живот", "тошн", "рвот")
_HEADACHE_MARKERS = ("голов", "головн")
_LIMB_MARKERS = re.compile(
    r"\b(ног\w*|рук\w*|колен\w*|сустав\w*|спин\w*|плеч\w*|шея)\b",
    re.I,
)
_MOOD_MARKERS = ("груст", "одинок", "тревож", "настроени")
_MEDICATION_MARKERS = ("таблет", "лекар", "препарат", "не помн", "забыл")

_DURATION_MARKERS = re.compile(
    r"\b(давно|дня|дней|недел|месяц|час|утр|вчера|сегодня|"
    r"второй\s+день|третий\s+день|пару\s+дней|несколько|с\s+утра|"
    r"уже\s+\w+\s+дн|в\s+четыре|в\s+\d+)\b",
    re.I,
)
_IMPROVING_MARKERS = re.compile(
    r"\b(уже\s+не\s+бол|почти\s+не\s+бол|прошл|легче|лучше|"
    r"уже\s+почти|вроде\s+прошл)\b",
    re.I,
)
_WAKE_MARKERS = re.compile(
    r"\b(проснул\w*|не\s+мог\w*\s+заснуть|в\s+\d+|часов?\s+\w+)\b",
    re.I,
)
_DAYTIME_MARKERS = re.compile(
    r"\b(дн[её]м|устал\w*|бодр\w*|нормально\s+сейчас|сейчас\s+норм)\b",
    re.I,
)


@dataclass(frozen=True)
class TopicPrompt:
    family: str
    dimension: str
    intent: str
    ack: str = ""


def _norm(text: str) -> str:
    return " ".join(
        text.lower()
        .replace("ё", "е")
        .replace(",", " ")
        .replace(".", " ")
        .split()
    )


def _split_clauses(text: str) -> list[str]:
    raw = text.lower().replace("ё", "е")
    raw = re.sub(r"[.!?]+", " ", raw)
    raw = re.sub(r"\s+(?:и\s+ещё|а\s+ещё|плюс)\s+", " || ", raw)
    parts = re.split(r"\s*,\s*|\s*;\s*|\s*\|\|\s*", raw)
    return [p.strip() for p in parts if p.strip()]


def detect_family_single(text: str) -> str | None:
    n = _norm(text)
    if not n:
        return None
    if any(m in n for m in _SLEEP_MARKERS) or ("спал" in n and any(
        x in n for x in ("плох", "не ", "мало", "час")
    )):
        return TopicFamily.SLEEP
    if any(m in n for m in _ABDOMINAL_MARKERS) and re.search(r"\b(бол|ноет|беспоко)\w*", n):
        return TopicFamily.ABDOMINAL_PAIN
    if any(m in n for m in _HEADACHE_MARKERS) and re.search(r"\b(бол|ноет|давит)\w*", n):
        return TopicFamily.HEADACHE
    if _LIMB_MARKERS.search(n) and re.search(r"\b(бол|ноет|ломит)\w*", n):
        return TopicFamily.LIMB_PAIN
    if any(m in n for m in _MOOD_MARKERS):
        return TopicFamily.MOOD
    if any(m in n for m in _MEDICATION_MARKERS):
        return TopicFamily.MEDICATION
    if re.search(r"\b(болит|боль|болел\w*|плохо\s+себя)\b", n):
        return TopicFamily.GENERAL_SYMPTOM
    return None


def detect_families(text: str) -> list[str]:
    """Detect issue families in priority order (deduplicated)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for clause in _split_clauses(text):
        family = detect_family_single(clause)
        if family and family not in seen:
            seen.add(family)
            ordered.append(family)
    if not ordered:
        single = detect_family_single(text)
        if single:
            ordered.append(single)
    return sorted(ordered, key=lambda f: _TOPIC_PRIORITY.index(f) if f in _TOPIC_PRIORITY else 99)


def infer_dimensions(family: str, text: str) -> list[str]:
    n = _norm(text)
    found: list[str] = []
    if family == TopicFamily.SLEEP:
        if _WAKE_MARKERS.search(n) or any(x in n for x in ("плохо спал", "не спал", "бессон", "проснул")):
            found.append("pattern")
        if _DAYTIME_MARKERS.search(n):
            found.append("daytime_impact")
    elif family == TopicFamily.ABDOMINAL_PAIN:
        if _IMPROVING_MARKERS.search(n) or re.search(r"\b(сейчас|уже)\b", n):
            found.append("current")
        if _DURATION_MARKERS.search(n):
            found.append("onset")
    elif family == TopicFamily.HEADACHE:
        if _DURATION_MARKERS.search(n):
            found.append("onset")
        if re.search(r"\b(сильн|слаб|хуже|лучше|прошл)\w*", n):
            found.append("severity")
    elif family == TopicFamily.LIMB_PAIN:
        if _DURATION_MARKERS.search(n):
            found.append("onset")
        if re.search(r"\b(ходить|двиг|подним|не\s+мог\w*)\b", n):
            found.append("function")
    elif family == TopicFamily.MOOD:
        if re.search(r"\b(плох\w*|груст\w*|хорош\w*|великолепн\w*)\b", n):
            found.append("intensity")
        if re.search(r"\b(одинок|сосед|друг|звонил|разговар)\w*", n):
            found.append("social")
    elif family == TopicFamily.GENERAL_SYMPTOM:
        if len(n.split()) >= 2:
            found.append("concern")
        if _DURATION_MARKERS.search(n):
            found.append("duration")
    return found


def _append_evidence(state: EngineState, family: str, text: str) -> None:
    clause = text.strip()
    if not clause:
        return
    bucket = state.topic_evidence.setdefault(family, [])
    if clause not in bucket:
        bucket.append(clause)


def _mark_dimensions(state: EngineState, family: str, dims: list[str]) -> None:
    bucket = state.topic_dimensions.setdefault(family, [])
    for dim in dims:
        if dim not in bucket:
            bucket.append(dim)


def prime_topics(state: EngineState, text: str, *, fallback: str | None = None) -> str | None:
    """Seed active/pending topics and inferred dimensions from user text."""
    families = detect_families(text)
    if fallback and fallback not in families:
        families = [fallback] + [f for f in families if f != fallback]
    if not families:
        return state.active_topic

    for family in families:
        _mark_dimensions(state, family, infer_dimensions(family, text))
        _append_evidence(state, family, text)

    if state.active_topic and state.active_topic not in families:
        if state.active_topic not in state.pending_topics:
            state.pending_topics.insert(0, state.active_topic)

    state.active_topic = families[0]
    for family in families[1:]:
        if family != state.active_topic and family not in state.pending_topics:
            state.pending_topics.append(family)
    return state.active_topic


def topic_slot(family: str) -> str:
    return f"topic_{family}"


def is_topic_slot(slot: str | None) -> bool:
    return bool(slot and slot.startswith("topic_"))


def family_from_slot(slot: str) -> str:
    return slot.removeprefix("topic_")


def observe_topic_answer(state: EngineState, text: str) -> None:
    """Update dimensions/evidence; handle topic switch mid-conversation."""
    family = state.active_topic
    if not family:
        return
    asked = state.topic_asked_dimension
    detected = detect_families(text)

    if detected and family not in detected:
        if not _topic_complete(state, family):
            if family not in state.pending_topics:
                state.pending_topics.insert(0, family)
        new_active = detected[0]
        for f in detected:
            _mark_dimensions(state, f, infer_dimensions(f, text))
            _append_evidence(state, f, text)
            if f != new_active and f not in state.pending_topics:
                state.pending_topics.append(f)
        state.active_topic = new_active
        state.topic_asked_dimension = None
        return

    inferred = infer_dimensions(family, text)
    if inferred:
        _mark_dimensions(state, family, inferred)
    elif asked and text.strip():
        _mark_dimensions(state, family, [asked])
    _append_evidence(state, family, text)


def _topic_complete(state: EngineState, family: str) -> bool:
    plan = TOPIC_PLANS.get(family, ())
    covered = set(state.topic_dimensions.get(family, []))
    return all(dim in covered for dim in plan)


def _activate_next_pending(state: EngineState) -> str | None:
    state.active_topic = None
    state.topic_asked_dimension = None
    while state.pending_topics:
        candidate = state.pending_topics.pop(0)
        if not _topic_complete(state, candidate):
            state.active_topic = candidate
            return candidate
    return None


def next_topic_prompt(state: EngineState) -> TopicPrompt | None:
    family = state.active_topic
    if not family:
        family = _activate_next_pending(state)
    if not family:
        return None
    plan = TOPIC_PLANS.get(family, ())
    covered = set(state.topic_dimensions.get(family, []))
    for dimension in plan:
        if dimension not in covered:
            state.topic_asked_dimension = dimension
            return TopicPrompt(
                family=family,
                dimension=dimension,
                intent=f"topic_{family}_{dimension}",
            )
    _complete_topic(state, family)
    return next_topic_prompt(state)


def _complete_topic(state: EngineState, family: str) -> None:
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.policy import apply_slot_answer

    slot = TOPIC_TO_SLOT.get(family)
    evidence = " ".join(state.topic_evidence.get(family, []))[:200]
    if slot and state.slots.get(slot) == SlotStatus.OPEN:
        polarity = "negative" if family != TopicFamily.SLEEP else None
        if family == TopicFamily.SLEEP:
            polarity = "negative" if re.search(r"\b(плох|не\s+спал|бессон)\w*", evidence) else "positive"
        apply_slot_answer(
            state,
            slot,
            evidence or family,
            polarity=polarity,
            confidence=0.88,
        )
    if family == TopicFamily.SLEEP and state.slots.get("mood") == SlotStatus.OPEN:
        pass  # sleep topic does not auto-skip mood
    state.active_topic = None
    state.topic_asked_dimension = None


def should_start_topic_flow(state: EngineState, text: str, *, answer_slot: str | None) -> bool:
    """Route into topic flow when user raises a concrete issue family."""
    if is_topic_slot(answer_slot):
        return True
    families = detect_families(text)
    if not families:
        return False
    if answer_slot == "wellness":
        return TopicFamily.SLEEP in families or TopicFamily.ABDOMINAL_PAIN in families
    if answer_slot and answer_slot.startswith("probe_"):
        return bool(
            {TopicFamily.SLEEP, TopicFamily.ABDOMINAL_PAIN} & set(families)
        )
    return False


def topic_ack_for_family(family: str) -> str:
    return {
        TopicFamily.SLEEP: "Понимаю.",
        TopicFamily.ABDOMINAL_PAIN: "Понятно.",
        TopicFamily.HEADACHE: "Понимаю.",
        TopicFamily.LIMB_PAIN: "Понимаю.",
        TopicFamily.MOOD: "Понимаю.",
        TopicFamily.GENERAL_SYMPTOM: "Понимаю.",
        TopicFamily.MEDICATION: "Хорошо.",
    }.get(family, "Понимаю.")
