"""Topic-based dialogue — active issue, pending queue, dimension tracking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState

from packages.dialogue_engine.state import TopicResolution


class TopicFamily(StrEnum):
    SLEEP = "sleep"
    ABDOMINAL_PAIN = "abdominal_pain"
    HEADACHE = "headache"
    LIMB_PAIN = "limb_pain"
    MOOD = "mood_loneliness"
    MEDICATION = "medication"
    GENERAL_SYMPTOM = "general_symptom"


TOPIC_PLANS: dict[str, tuple[str, ...]] = {
    TopicFamily.SLEEP: ("quality", "pattern", "daytime_impact"),
    TopicFamily.ABDOMINAL_PAIN: ("current", "onset"),
    TopicFamily.HEADACHE: ("onset", "severity"),
    TopicFamily.LIMB_PAIN: ("onset", "function"),
    TopicFamily.MOOD: ("intensity", "social"),
    TopicFamily.MEDICATION: ("status_today",),
    TopicFamily.GENERAL_SYMPTOM: ("concern", "duration"),
}

# Dimensions inferred only — never spoken as a standalone question.
_INFER_ONLY_DIMENSIONS: dict[str, frozenset[str]] = {
    TopicFamily.SLEEP: frozenset({"quality"}),
}

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

_SLEEP_QUALITY_MARKERS = (
    "плохо спал",
    "плохо спала",
    "не высп",
    "не спал",
    "не спала",
    "бессон",
    "сон плох",
    "мало спал",
    "мало спала",
)
_SLEEP_PATTERN_MARKERS = (
    "проснул",
    "проснула",
    "не мог заснуть",
    "не могла заснуть",
    "не засып",
    "часов",
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
    r"\b(давно|дня|дней|недел\w*|месяц\w*|час\w*|утр\w*|вчера|сегодня|"
    r"второй\s+день|третий\s+день|пару\s+дней|несколько|с\s+утра|"
    r"уже\s+\w+\s+дн|в\s+четыре|в\s+\d+)\b",
    re.I,
)
_IMPROVING_MARKERS = re.compile(
    r"\b(почти\s+не\s+бол\w*|уже\s+почти|вроде\s+прошл)\b",
    re.I,
)
_RESOLVED_MARKERS = re.compile(
    r"\b(уже\s+не\s+бол|не\s+болит|прошл\w*|легче|лучше)\b",
    re.I,
)
_WAKE_MARKERS = re.compile(
    r"\b(проснул\w*|не\s+мог\w*\s+заснуть|в\s+\d+|в\s+четыре|часов?\s+\w+)\b",
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


@dataclass
class TopicIngestResult:
    families: list[str] = field(default_factory=list)


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


def _clause_has_sleep(n: str) -> bool:
    if any(m in n for m in _SLEEP_QUALITY_MARKERS):
        return True
    if any(m in n for m in _SLEEP_PATTERN_MARKERS):
        return True
    return "спал" in n and any(x in n for x in ("плох", "не ", "мало", "час"))


def _clause_has_abdominal(n: str) -> bool:
    if not any(m in n for m in _ABDOMINAL_MARKERS):
        return False
    if re.search(r"\b(бол|ноет|беспоко|побалив)\w*", n):
        return True
    return bool(re.search(r"\bиз[\s-]*за\b", n.replace("-", " ")))


def detect_families_in_clause(clause: str) -> list[str]:
    """Return ALL families present in one clause — no early return."""
    n = _norm(clause)
    if not n:
        return []
    found: list[str] = []
    if _clause_has_sleep(n):
        found.append(TopicFamily.SLEEP)
    if _clause_has_abdominal(n):
        found.append(TopicFamily.ABDOMINAL_PAIN)
    if any(m in n for m in _HEADACHE_MARKERS) and re.search(
        r"\b(бол|ноет|давит)\w*", n
    ):
        found.append(TopicFamily.HEADACHE)
    if _LIMB_MARKERS.search(n) and re.search(r"\b(бол|ноет|ломит)\w*", n):
        found.append(TopicFamily.LIMB_PAIN)
    if any(m in n for m in _MOOD_MARKERS):
        found.append(TopicFamily.MOOD)
    if any(m in n for m in _MEDICATION_MARKERS):
        found.append(TopicFamily.MEDICATION)
    if re.search(r"\b(болит|боль|болел\w*|плохо\s+себя)\b", n):
        specific = {
            TopicFamily.ABDOMINAL_PAIN,
            TopicFamily.HEADACHE,
            TopicFamily.LIMB_PAIN,
        }
        if not specific.intersection(found):
            found.append(TopicFamily.GENERAL_SYMPTOM)
    return found


def detect_families(text: str) -> list[str]:
    """Detect issue families in priority order (deduplicated)."""
    seen: set[str] = set()
    ordered: list[str] = []
    clauses = _split_clauses(text) or [text]
    for clause in clauses:
        for family in detect_families_in_clause(clause):
            if family not in seen:
                seen.add(family)
                ordered.append(family)
    return sorted(ordered, key=lambda f: _TOPIC_PRIORITY.index(f) if f in _TOPIC_PRIORITY else 99)


def _extract_temporal_anchors(text: str) -> list[str]:
    return [m.group(0).lower() for m in _DURATION_MARKERS.finditer(_norm(text))]


def infer_dimensions(
    family: str,
    text: str,
    *,
    turn_context: str | None = None,
) -> list[str]:
    """Infer dimensions from clause text, optionally using full turn context."""
    n = _norm(text)
    ctx = _norm(turn_context or text)
    found: list[str] = []

    if family == TopicFamily.SLEEP:
        if any(x in n for x in _SLEEP_QUALITY_MARKERS) or (
            "спал" in n and "плох" in n
        ):
            found.append("quality")
        if _WAKE_MARKERS.search(n) or any(x in n for x in _SLEEP_PATTERN_MARKERS):
            found.append("pattern")
        if _DAYTIME_MARKERS.search(n):
            found.append("daytime_impact")

    elif family == TopicFamily.ABDOMINAL_PAIN:
        if _IMPROVING_MARKERS.search(n) or (
            re.search(r"\b(сейчас|уже)\b", n) and re.search(r"\b(бол|ноет)\w*", n)
        ):
            found.append("current")
        if _RESOLVED_MARKERS.search(n) and "живот" in n:
            found.append("current")
        if _duration_satisfied_from_text(n, ctx, family_clause=n):
            found.append("onset")

    elif family == TopicFamily.HEADACHE:
        if _duration_satisfied_from_text(n, ctx, family_clause=n):
            found.append("onset")
        if re.search(r"\b(сильн|слаб|хуже|лучше|прошл)\w*", n):
            found.append("severity")

    elif family == TopicFamily.LIMB_PAIN:
        if _duration_satisfied_from_text(n, ctx, family_clause=n):
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
        if _duration_satisfied_from_text(n, ctx, family_clause=n):
            found.append("duration")

    return found


def _duration_satisfied_from_text(
    clause: str,
    turn_context: str,
    *,
    family_clause: str,
) -> bool:
    """Temporal priority: clause anchor > turn context; conflict → False."""
    clause_anchors = _extract_temporal_anchors(clause)
    if clause_anchors:
        return True
    ctx_anchors = _extract_temporal_anchors(turn_context)
    if not ctx_anchors:
        return False
    family_anchors = _extract_temporal_anchors(family_clause)
    if family_anchors and family_anchors != ctx_anchors:
        return False
    return True


def _append_topic_evidence(
    state: EngineState,
    family: str,
    clause: str,
    turn_text: str,
) -> None:
    from packages.dialogue_engine.state import TopicEvidence as TE

    clause = clause.strip()
    turn_text = turn_text.strip()
    if not clause:
        return
    bucket = state.topic_evidence.setdefault(family, [])
    for existing in bucket:
        if existing.clause == clause and existing.turn_text == turn_text:
            return
    bucket.append(TE(clause=clause, turn_text=turn_text))


def _mark_dimensions(state: EngineState, family: str, dims: list[str]) -> None:
    bucket = state.topic_dimensions.setdefault(family, [])
    for dim in dims:
        if dim not in bucket:
            bucket.append(dim)


def _update_resolution(state: EngineState, family: str, clause: str) -> None:
    n = _norm(clause)
    if family == TopicFamily.ABDOMINAL_PAIN:
        if _IMPROVING_MARKERS.search(n):
            state.topic_resolution[family] = TopicResolution.IMPROVING
        elif _RESOLVED_MARKERS.search(n) and "живот" in n:
            state.topic_resolution[family] = TopicResolution.RESOLVED
        elif family not in state.topic_resolution:
            state.topic_resolution[family] = TopicResolution.OPEN


def _sort_by_priority(families: list[str]) -> list[str]:
    return sorted(
        families,
        key=lambda f: _TOPIC_PRIORITY.index(f) if f in _TOPIC_PRIORITY else 99,
    )


def _topic_complete(state: EngineState, family: str) -> bool:
    plan = TOPIC_PLANS.get(family, ())
    for dim in plan:
        if not dimensions_satisfied(state, family, dim):
            return False
    return True


def dimensions_satisfied(state: EngineState, family: str, dimension: str) -> bool:
    if dimension in state.topic_dimensions.get(family, []):
        return True

    evidences = state.topic_evidence.get(family, [])
    if not evidences:
        return False

    if family == TopicFamily.ABDOMINAL_PAIN and dimension == "current":
        res = state.topic_resolution.get(family)
        if res in (TopicResolution.IMPROVING, TopicResolution.RESOLVED):
            return True
        for ev in evidences:
            if _IMPROVING_MARKERS.search(_norm(ev.clause)) or _RESOLVED_MARKERS.search(
                _norm(ev.clause)
            ):
                return True

    if dimension == "onset" or dimension == "duration":
        for ev in evidences:
            if _duration_satisfied_from_text(
                ev.clause, ev.turn_text, family_clause=ev.clause
            ):
                return True
        return False

    combined = " ".join(ev.clause for ev in evidences)
    ctx = evidences[-1].turn_text if evidences else combined
    inferred = infer_dimensions(family, combined, turn_context=ctx)
    return dimension in inferred


def _apply_focus_policy(state: EngineState, detected: list[str]) -> None:
    if not detected:
        return
    ordered = _sort_by_priority(detected)
    active = state.active_topic

    if active and not _topic_complete(state, active):
        for family in ordered:
            if family != active and family not in state.pending_topics:
                state.pending_topics.append(family)
        return

    if active and _topic_complete(state, active):
        _complete_topic(state, active)
        state.active_topic = None
        active = None

    if not state.active_topic:
        for family in ordered:
            if not _topic_complete(state, family):
                state.active_topic = family
                break
        for family in ordered:
            if (
                family != state.active_topic
                and family not in state.pending_topics
                and not _topic_complete(state, family)
            ):
                state.pending_topics.append(family)


def ingest_user_turn_topics(
    state: EngineState,
    text: str,
    *,
    fallback: str | None = None,
) -> TopicIngestResult:
    """Ingest every family from every clause; update evidence, dimensions, focus."""
    if state.uses_issue_episodes():
        return _ingest_sleep_hints_only(state, text, fallback=fallback)
    turn_text = text.strip()
    if not turn_text:
        return TopicIngestResult()

    detected: list[str] = []
    clauses = _split_clauses(turn_text) or [turn_text]
    for clause in clauses:
        families = detect_families_in_clause(clause)
        for family in families:
            if family not in detected:
                detected.append(family)
            _append_topic_evidence(state, family, clause, turn_text)
            dims = infer_dimensions(family, clause, turn_context=turn_text)
            _mark_dimensions(state, family, dims)
            _update_resolution(state, family, clause)

    if fallback and fallback not in detected:
        detected.insert(0, fallback)
        _append_topic_evidence(state, fallback, turn_text, turn_text)
        _mark_dimensions(
            state, fallback, infer_dimensions(fallback, turn_text, turn_context=turn_text)
        )

    if state.active_topic and turn_text:
        fam = state.active_topic
        dims = infer_dimensions(fam, turn_text, turn_context=turn_text)
        _mark_dimensions(state, fam, dims)

    _apply_focus_policy(state, _sort_by_priority(detected))

    return TopicIngestResult(families=_sort_by_priority(detected))


def _ingest_sleep_hints_only(
    state: EngineState,
    text: str,
    *,
    fallback: str | None = None,
) -> TopicIngestResult:
    """When IssueEpisode memory is canonical, only sleep fast-hints remain."""
    turn_text = text.strip()
    if not turn_text:
        return TopicIngestResult()
    detected: list[str] = []
    n = _norm(turn_text)
    if _clause_has_sleep(n):
        detected.append(TopicFamily.SLEEP)
        _append_topic_evidence(state, TopicFamily.SLEEP, turn_text, turn_text)
        dims = infer_dimensions(TopicFamily.SLEEP, turn_text, turn_context=turn_text)
        _mark_dimensions(state, TopicFamily.SLEEP, dims)
    if fallback == TopicFamily.SLEEP and TopicFamily.SLEEP not in detected:
        detected.insert(0, TopicFamily.SLEEP)
    if state.active_topic and turn_text:
        fam = state.active_topic
        if fam not in detected:
            detected.append(fam)
        _append_topic_evidence(state, fam, turn_text, turn_text)
        dims = infer_dimensions(fam, turn_text, turn_context=turn_text)
        _mark_dimensions(state, fam, dims)
        _update_resolution(state, fam, turn_text)
    if detected:
        _apply_focus_policy(state, _sort_by_priority(detected))
    return TopicIngestResult(families=_sort_by_priority(detected))


def sync_topic_hints_from_answer(state: EngineState, text: str, *, answer_slot: str | None) -> None:
    """Keep Phase 1 sleep/abdominal topic hints when rich episodes are canonical."""
    if not is_topic_slot(answer_slot) and not (
        answer_slot and answer_slot.startswith("topic_")
    ):
        return
    n = _norm(text)
    turn_text = text.strip()
    if _clause_has_sleep(n) or state.active_topic == TopicFamily.SLEEP:
        _append_topic_evidence(state, TopicFamily.SLEEP, turn_text, turn_text)
        dims = infer_dimensions(TopicFamily.SLEEP, turn_text, turn_context=turn_text)
        _mark_dimensions(state, TopicFamily.SLEEP, dims)
    if re.search(r"\bживот\w*\b", n) and re.search(r"\b(бол|ноет)\w*", n):
        _append_topic_evidence(state, TopicFamily.ABDOMINAL_PAIN, turn_text, turn_text)
        dims = infer_dimensions(
            TopicFamily.ABDOMINAL_PAIN, turn_text, turn_context=turn_text
        )
        _mark_dimensions(state, TopicFamily.ABDOMINAL_PAIN, dims)
        if (
            state.active_topic != TopicFamily.ABDOMINAL_PAIN
            and TopicFamily.ABDOMINAL_PAIN not in state.pending_topics
        ):
            state.pending_topics.append(TopicFamily.ABDOMINAL_PAIN)


def prime_topics(state: EngineState, text: str, *, fallback: str | None = None) -> str | None:
    ingest_user_turn_topics(state, text, fallback=fallback)
    return state.active_topic


def topic_slot(family: str) -> str:
    return f"topic_{family}"


def is_topic_slot(slot: str | None) -> bool:
    return bool(slot and slot.startswith("topic_"))


def family_from_slot(slot: str) -> str:
    return slot.removeprefix("topic_")


def observe_topic_answer(state: EngineState, text: str) -> TopicIngestResult:
    return ingest_user_turn_topics(state, text)


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
    infer_only = _INFER_ONLY_DIMENSIONS.get(family, frozenset())

    for dimension in plan:
        if dimension in infer_only and dimensions_satisfied(state, family, dimension):
            continue
        if not dimensions_satisfied(state, family, dimension):
            state.topic_asked_dimension = dimension
            return TopicPrompt(
                family=family,
                dimension=dimension,
                intent=f"topic_{family}_{dimension}",
            )

    _complete_topic(state, family)
    return next_topic_prompt(state)


def _evidence_text(state: EngineState, family: str) -> str:
    parts = [ev.clause for ev in state.topic_evidence.get(family, [])]
    return " ".join(parts)[:200]


def _complete_topic(state: EngineState, family: str) -> None:
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.policy import apply_slot_answer

    slot = TOPIC_TO_SLOT.get(family)
    evidence = _evidence_text(state, family)
    if slot and state.slots.get(slot) == SlotStatus.OPEN:
        polarity = None
        if family == TopicFamily.SLEEP:
            polarity = (
                "negative"
                if re.search(r"\b(плох|не\s+спал|бессон)\w*", evidence)
                else "positive"
            )
        apply_slot_answer(
            state,
            slot,
            evidence or family,
            polarity=polarity,
            confidence=0.88,
        )
    state.active_topic = None
    state.topic_asked_dimension = None


_BACKGROUND_CHECK_SLOTS = frozenset({"sleep"})

_CONCRETE_SYMPTOM_FAMILIES = frozenset(
    {
        TopicFamily.ABDOMINAL_PAIN,
        TopicFamily.HEADACHE,
        TopicFamily.LIMB_PAIN,
        TopicFamily.GENERAL_SYMPTOM,
    }
)


def should_start_topic_flow(state: EngineState, text: str, *, answer_slot: str | None) -> bool:
    if state.uses_issue_episodes():
        if is_topic_slot(answer_slot):
            return True
        n = _norm(text)
        if answer_slot in _BACKGROUND_CHECK_SLOTS or answer_slot == "wellness":
            return _clause_has_sleep(n)
        return False
    if is_topic_slot(answer_slot):
        return True
    families = detect_families(text)
    if not families:
        return False
    if answer_slot in _BACKGROUND_CHECK_SLOTS:
        return bool(_CONCRETE_SYMPTOM_FAMILIES.intersection(families))
    if answer_slot == "wellness":
        return TopicFamily.SLEEP in families or TopicFamily.ABDOMINAL_PAIN in families
    if answer_slot and answer_slot.startswith("probe_"):
        return bool({TopicFamily.SLEEP, TopicFamily.ABDOMINAL_PAIN} & set(families))
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
