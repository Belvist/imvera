"""Daily-check branching — table-driven wellness paths and probe transitions."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState

_PAIN = re.compile(
    r"\b(болит|боль|болел\w*|болела|голова|головн\w*|живот|спина|сустав|"
    r"давлен\w*|температур\w*|кашел\w*|тошн\w*|слабост\w*|одышк\w*)\b",
    re.I,
)
_SYMPTOM_DETAIL = re.compile(
    r"\b(кружит\w*|тошн\w*|слабост\w*|одышк\w*|температур\w*|"
    r"вс[её]\s+болит|ничего\s+не\s+радует)\b",
    re.I,
)
_URGENT = re.compile(
    r"\b(скор\w*|срочн\w*|помогите|спасите|не\s+могу\s+дышать|"
    r"кровь|потеря\w*\s+сознан|очень\s+сильн\w*|ужасн\w*\s+боль|"
    r"вызов\w*\s+скор\w*|инфаркт|инсульт|сердечн\w*\s+приступ)\b",
    re.I,
)
_DURATION_HINT = re.compile(
    r"\b(давно|дня|дней|недел|месяц|час|утр|вчера|сегодня|"
    r"второй\s+день|третий\s+день|пару\s+дней|несколько|с\s+утра|"
    r"уже\s+\w+\s+дн)\b",
    re.I,
)
_SYMPTOM_HEAD = re.compile(r"\b(голов\w*|головн\w*\s+бол\w*)\b", re.I)
_SYMPTOM_STOMACH = re.compile(r"\b(живот|тошн\w*|рвот\w*)\b", re.I)
_SYMPTOM_BACK = re.compile(r"\b(спин\w*|поясниц\w*)\b", re.I)
_SYMPTOM_PRESSURE = re.compile(r"\b(давлен\w*|гипертон\w*)\b", re.I)
_OK_BUT_PAIN = re.compile(
    r"\b(нормально|хорошо|терпимо|сойд\w*|пойд\w*)\b",
    re.I,
)
_CONTRAST = re.compile(r"\b(но|хотя)\b", re.I)


class ProbeAction(StrEnum):
    SPEAK_PROBE = "speak_probe"
    SPEAK_SLOT = "speak_slot"
    SPEAK_PLANS = "speak_plans"
    URGENT_CLOSE = "urgent_close"
    CONTINUE_LADDER = "continue_ladder"


@dataclass(frozen=True)
class WellnessBranch:
    """First matching rule wins — explicit priority, no nested if/else."""

    path: str
    probe_phase: str | None = None
    skip_mood_sleep: bool = False
    store_concern_from_wellness: bool = False
    urgent: bool = False


@dataclass(frozen=True)
class ProbeStep:
    action: ProbeAction
    probe_phase: str | None = None
    next_slot: str | None = None
    ack_polarity: str | None = None


def has_pain_mention(text: str) -> bool:
    return bool(_PAIN.search(text or ""))


def has_symptom_detail(text: str) -> bool:
    return has_pain_mention(text) or bool(_SYMPTOM_DETAIL.search(text or ""))


def wellness_already_describes_concern(text: str) -> bool:
    """Wellness answer already names symptoms — skip redundant probe_concern."""
    normalized = (text or "").strip()
    if not normalized:
        return False
    if has_symptom_detail(normalized):
        return True
    lower = normalized.lower()
    if len(lower.split()) >= 5 and re.search(r"\b(плох\w*|беспоко\w*|болит)\b", lower):
        return True
    return False


def is_urgent_concern(text: str) -> bool:
    return bool(_URGENT.search(text or ""))


def looks_like_duration_answer(text: str) -> bool:
    normalized = (text or "").lower().strip()
    if not normalized:
        return False
    if is_urgent_concern(normalized):
        return True
    if _DURATION_HINT.search(normalized):
        return True
    if re.match(r"^\d+\s*(час|день|дн|недел)", normalized):
        return True
    return len(normalized.split()) >= 2


def _pain_ok_but(text: str) -> bool:
    return bool(_CONTRAST.search(text) and _OK_BUT_PAIN.search(text) and has_pain_mention(text))


def classify_wellness_path(
    *,
    wellness_text: str,
    polarity: str | None,
) -> WellnessBranch:
    from packages.dialogue_engine.state import CheckPath
    from packages.dialogue_engine.topic_tracker import TopicFamily, detect_families

    text = (wellness_text or "").lower()
    rules: tuple[tuple[Callable[[], bool], WellnessBranch], ...] = (
        (
            lambda: TopicFamily.SLEEP in detect_families(text),
            WellnessBranch(path=CheckPath.STANDARD),
        ),
        (
            lambda: is_urgent_concern(text),
            WellnessBranch(path=CheckPath.URGENT, urgent=True, store_concern_from_wellness=True),
        ),
        (
            lambda: _pain_ok_but(text),
            WellnessBranch(
                path=CheckPath.PAIN_SHORT,
                probe_phase="pain_night",
                skip_mood_sleep=True,
                store_concern_from_wellness=True,
            ),
        ),
        (
            lambda: has_pain_mention(text) and polarity in (None, "positive", "uncertain"),
            WellnessBranch(
                path=CheckPath.PAIN_SHORT,
                probe_phase="pain_night",
                skip_mood_sleep=True,
                store_concern_from_wellness=True,
            ),
        ),
        (
            lambda: polarity == "negative" and wellness_already_describes_concern(text),
            WellnessBranch(
                path=CheckPath.NEGATIVE_PROBE,
                probe_phase="duration",
                store_concern_from_wellness=True,
            ),
        ),
        (
            lambda: polarity == "negative",
            WellnessBranch(path=CheckPath.NEGATIVE_PROBE, probe_phase="concern"),
        ),
        (
            lambda: has_pain_mention(text),
            WellnessBranch(
                path=CheckPath.PAIN_SHORT,
                probe_phase="pain_night",
                skip_mood_sleep=True,
                store_concern_from_wellness=True,
            ),
        ),
    )
    for matches, branch in rules:
        if matches():
            return branch
    return WellnessBranch(path=CheckPath.STANDARD)


def apply_wellness_branch(state: EngineState, branch: WellnessBranch) -> None:
    state.check_path = branch.path
    if branch.store_concern_from_wellness:
        state.wellness_concern = state.slot_values.get("wellness", "")
    if branch.skip_mood_sleep:
        state.skipped_slots.update({"mood", "sleep"})
    state.probe_phase = branch.probe_phase


_PROBE_FLOW: dict[str, Callable[[EngineState, str], ProbeStep]] = {}


def _register_probe(phase: str, handler: Callable[[EngineState, str], ProbeStep]) -> None:
    _PROBE_FLOW[phase] = handler


def _probe_concern(state: EngineState, text: str) -> ProbeStep:
    from packages.dialogue_engine.state import CheckPath

    state.wellness_concern = text
    if is_urgent_concern(text):
        state.check_path = CheckPath.URGENT
        state.probe_phase = None
        return ProbeStep(action=ProbeAction.URGENT_CLOSE)
    state.probe_phase = "duration"
    return ProbeStep(action=ProbeAction.SPEAK_PROBE, probe_phase="duration")


def _probe_duration(state: EngineState, text: str) -> ProbeStep:
    from packages.dialogue_engine.issue_memory import extract_grounded_onset_value
    from packages.dialogue_engine.state import CheckPath

    state.wellness_duration = text
    state.probe_phase = None
    if is_urgent_concern(text) or is_urgent_concern(state.wellness_concern):
        state.check_path = CheckPath.URGENT
        return ProbeStep(action=ProbeAction.URGENT_CLOSE)
    if state.active_episode_id:
        ep = state.issue_episodes.get(state.active_episode_id)
        if ep is not None:
            duration = extract_grounded_onset_value(text)
            if duration:
                ep.known_attributes["duration"] = duration
            return ProbeStep(action=ProbeAction.CONTINUE_LADDER)
    next_slot = state.next_open_slot()
    return ProbeStep(
        action=ProbeAction.SPEAK_SLOT,
        next_slot=next_slot,
        ack_polarity="negative",
    )


def _probe_pain_night(state: EngineState, text: str) -> ProbeStep:
    state.pain_at_night = text
    state.probe_phase = None
    return ProbeStep(action=ProbeAction.SPEAK_PLANS)


_register_probe("concern", _probe_concern)
_register_probe("duration", _probe_duration)
_register_probe("pain_night", _probe_pain_night)


def advance_probe_phase(state: EngineState, text: str) -> ProbeStep:
    phase = state.probe_phase
    if not phase:
        return ProbeStep(action=ProbeAction.CONTINUE_LADDER)
    handler = _PROBE_FLOW.get(phase)
    if handler is None:
        state.probe_phase = None
        return ProbeStep(action=ProbeAction.CONTINUE_LADDER)
    return handler(state, text)


def symptom_followup_label(concern: str) -> str | None:
    text = concern or ""
    if _SYMPTOM_HEAD.search(text):
        return "головная боль"
    if _SYMPTOM_STOMACH.search(text):
        return "живот"
    if _SYMPTOM_BACK.search(text):
        return "спина"
    if _SYMPTOM_PRESSURE.search(text):
        return "давление"
    if has_pain_mention(text):
        return "самочувствие"
    return None


_FOLLOWUP_BY_SYMPTOM: dict[str, str] = {
    "head": "Прошлый раз вы говорили о головной боли. Как сейчас голова?",
    "живот": "Прошлый раз беспокоил живот. Как сейчас?",
    "спина": "Прошлый раз болела спина. Как сейчас?",
    "давление": "Прошлый раз вы говорили о давлении. Как сейчас?",
}


def prior_followup_question(prior: dict[str, str]) -> str | None:
    concern = (
        prior.get("wellness_concern")
        or prior.get("wellness_detail")
        or prior.get("symptom_followup")
        or ""
    ).strip()
    if not concern:
        return None
    label = symptom_followup_label(concern) or concern
    if "голов" in label:
        return _FOLLOWUP_BY_SYMPTOM["head"]
    if label in _FOLLOWUP_BY_SYMPTOM:
        return _FOLLOWUP_BY_SYMPTOM[label]
    short = label[:60].rstrip("., ")
    return f"Прошлый раз вы говорили: {short}. Как сейчас себя чувствуете?"


def build_call_metadata(state: EngineState) -> dict[str, str]:
    from packages.dialogue_engine.state import CheckPath

    meta: dict[str, str] = {}
    if state.wellness_concern:
        meta["wellness_concern"] = state.wellness_concern
        label = symptom_followup_label(state.wellness_concern)
        if label:
            meta["symptom_followup"] = label
    if state.wellness_duration:
        meta["wellness_duration"] = state.wellness_duration
    if state.pain_at_night:
        meta["pain_at_night"] = state.pain_at_night
    if state.check_path != CheckPath.STANDARD:
        meta["check_path"] = state.check_path.value
    return meta
