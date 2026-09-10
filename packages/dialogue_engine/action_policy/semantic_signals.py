"""Canonical semantic signals for ActionPolicy — no legacy check_path/probe inputs."""

from __future__ import annotations

import re

from packages.dialogue_engine.semantic_kernel.types import SubjectKind

_WELLNESS_NEGATIVE = frozenset({"negative", "uncertain", "bad", "poor"})
_ISSUE_ATTRIBUTES = frozenset({"issue"})
_URGENT_RISK_TEXT = re.compile(
    r"\b(скор\w*|срочн\w*|помогите|спасите|не\s+могу\s+дышать|"
    r"кровь|потеря\w*\s+сознан|очень\s+сильн\w*|ужасн\w*\s+боль|"
    r"вызов\w*\s+скор\w*|инфаркт|инсульт|сердечн\w*\s+приступ)\b",
    re.I,
)
_URGENT_RISK_KINDS = frozenset({"fall", "cannot_stand", "help_request"})
_SPEAKER_OK = re.compile(
    r"\b(я\s+нормально|мне\s+нормально|я\s+в\s+порядке|со\s+мной\s+вс[её]\s+хорошо)\b",
    re.I,
)
_SPEAKER_UNWELL = re.compile(
    r"\b(мне\s+самому\s+плохо|мне\s+плохо|я\s+.*плохо|чувствую\s+себя\s+плохо)\b",
    re.I,
)


def _subject_kind(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw).strip().lower()


def _observation_is_issue(obs: object) -> bool:
    attribute = str(getattr(obs, "attribute", "")).strip().lower()
    if attribute in _ISSUE_ATTRIBUTES:
        return True
    return bool(str(getattr(obs, "issue_normalized", "")).strip())


def classify_turn_issues(
    *,
    issue_mentions: tuple[object, ...] = (),
    observations: tuple[object, ...] = (),
) -> tuple[bool, bool]:
    """Return (has_speaker_issue, has_other_person_issue) from kernel observations."""
    speaker = False
    other = False
    for obs in observations:
        if not _observation_is_issue(obs):
            continue
        subject = _subject_kind(getattr(obs, "subject", SubjectKind.UNKNOWN))
        if subject == SubjectKind.OTHER_PERSON.value:
            other = True
        elif subject == SubjectKind.SPEAKER.value:
            speaker = True
    if observations:
        return speaker, other
    if issue_mentions:
        # Corpus / legacy path without observations — treat as speaker-owned mention.
        return True, False
    return False, False


def has_grounded_speaker_issue(
    issue_mentions: tuple[object, ...] = (),
    observations: tuple[object, ...] = (),
) -> bool:
    speaker, _ = classify_turn_issues(
        issue_mentions=issue_mentions,
        observations=observations,
    )
    return speaker


def _speaker_wellness_negative(goal_facts: tuple[object, ...]) -> bool:
    for fact in goal_facts:
        if getattr(fact, "field", None) != "wellness":
            continue
        subject = str(getattr(fact, "subject", "speaker")).strip().lower()
        if subject not in {"speaker", "unknown"}:
            continue
        value = str(getattr(fact, "value", "")).strip().lower()
        if value in _WELLNESS_NEGATIVE:
            return True
    return False


def wellness_polarity_negative(goal_facts: tuple[object, ...]) -> bool:
    return _speaker_wellness_negative(goal_facts)


def derive_unresolved_concern(
    *,
    raw_text: str = "",
    issue_mentions: tuple[object, ...] = (),
    goal_facts: tuple[object, ...] = (),
    kernel_ambiguities: tuple[str, ...] = (),
    needs_clarification: bool = False,
    observations: tuple[object, ...] = (),
) -> bool:
    """Negative/uncertain wellness without a grounded speaker issue → clarify concern."""
    speaker_issue, other_issue = classify_turn_issues(
        issue_mentions=issue_mentions,
        observations=observations,
    )
    if speaker_issue:
        return False
    if other_issue and not speaker_issue:
        if _SPEAKER_OK.search(raw_text or ""):
            return False
        if _SPEAKER_UNWELL.search(raw_text or "") or _speaker_wellness_negative(goal_facts):
            return True
        return False
    if needs_clarification:
        return True
    if "vague_issue" in kernel_ambiguities:
        return True
    return _speaker_wellness_negative(goal_facts)


def derive_turn_risk_level(
    *,
    raw_text: str = "",
    risk_candidates: tuple[object, ...] = (),
) -> str:
    """Canonical current-turn safety signal — not legacy EngineState.check_path."""
    for risk in risk_candidates:
        if str(getattr(risk, "proposal", "")).strip().lower() == "dismiss":
            continue
        kind = str(getattr(risk, "kind", "")).strip().lower()
        subject = str(getattr(risk, "subject", "speaker")).strip().lower()
        if kind in _URGENT_RISK_KINDS and subject in {"speaker", "unknown"}:
            return "urgent"
    if _URGENT_RISK_TEXT.search(raw_text or ""):
        return "urgent"
    return "none"
