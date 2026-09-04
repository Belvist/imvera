"""Turn analysis — classification and fact extraction only."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from golden_path.semantics import (
    detect_slot_answer,
    extract_correction_symptom,
    extract_symptom_code,
    is_user_fatigue,
    is_wait_request,
    slot_from_text,
)
from golden_path.slots import SlotName, is_refusal
from golden_path.state import ConversationState


class AnalysisKind(str, Enum):
    DIRECT_USER_QUESTION = "DIRECT_USER_QUESTION"
    CORRECTION = "CORRECTION"
    REPAIR = "REPAIR"
    TOPIC_REFUSAL = "TOPIC_REFUSAL"
    NORMAL_RESPONSE = "NORMAL_RESPONSE"
    SAFETY = "SAFETY"
    GOODBYE = "GOODBYE"
    WAIT_REQUEST = "WAIT_REQUEST"
    USER_FATIGUE = "USER_FATIGUE"


class AnswerType(str, Enum):
    IDENTITY = "IDENTITY"
    WHY_CALLING = "WHY_CALLING"
    PRIVACY = "PRIVACY"
    REPEAT_LAST_QUESTION = "REPEAT_LAST_QUESTION"
    OTHER = "OTHER"


SAFETY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bупал[аи]?\b",
        r"\bупала\b",
        r"\bне\s+могу\s+встать\b",
        r"\bне\s+встаю\b",
        r"\bсильно\s+болит\b",
        r"\bне\s+дыш",
        r"\bтрудно\s+дыш",
        r"\bскорую\b",
        r"\bвызовите\b",
        r"\bнеотложн",
        r"\bсрочно\s+помог",
        r"\bтемператур[аы]\s+(высок|39|40)",
    )
)

REPAIR_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"что\s+ты\s+сказал",
        r"что\s+вы\s+сказал",
        r"повтори",
        r"повторите",
        r"ещё\s+раз",
        r"еще\s+раз",
        r"не\s+расслышал",
        r"не\s+расслышала",
        r"не\s+понял",
        r"не\s+поняла",
        r"как\s+вы\s+сказал",
        r"скажите\s+снова",
        r"что\s+ты\s+.*спросил",
        r"что\s+вы\s+.*спросил",
        r"перед\s+этим\s+спросил",
    )
)

CORRECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bне\s+голов\w*\b",
        r"\bне\s+спин\w*\b",
        r"\bя\s+имел\s+в\s+виду\b",
        r"\bя\s+имела\s+в\s+виду\b",
        r"\bисправ\w*\b",
        r"\bнет,\s*не\s+\w+\b",
        r"\bна\s+самом\s+деле\b",
        r"\bэто\s+не\s+\w+\b",
        r"\bа\s+не\s+\w+\b",
        r"\bоговорил\w*\b",
    )
)

QUESTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\?\s*$",
        r"^(кто|что|где|когда|почему|зачем|как|сколько)\b",
        r"\bвы\s+кто\b",
        r"\bкак\s+вас\s+зовут\b",
        r"\bчто\s+такое\s+имвера\b",
        r"\bзачем\s+вы\s+звон",
    )
)

GOODBYE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bдо\s+свидан",
        r"\bпока\b",
        r"\bвсего\s+добр",
        r"\bпрощай",
        r"\bзакончим\b",
        r"\bхватит\b",
        r"\bвсё,\s+спасибо\b",
    )
)

PRIVACY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bпаспорт",
        r"\bадрес",
        r"\bкарта\b",
        r"\bпин[\s-]?код",
        r"\bснилс",
        r"\bпарол",
        r"\bувидят\b",
        r"\bувидит\b",
        r"\bкто\s+увидит",
        r"\bкому\s+переда",
        r"\bконфиденциал",
        r"\bличн\w+\s+данн",
    )
)

IDENTITY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bвы\s+кто\b",
        r"\bкто\s+вы\b",
        r"\bкак\s+вас\s+зовут\b",
        r"\bкак\s+тебя\s+зовут\b",
        r"\bчто\s+такое\s+имвера\b",
        r"\bчто\s+за\s+сервис\b",
    )
)

WHY_CALLING_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"зачем.*звон",
        r"почему.*звон",
        r"\bдля\s+чего\s+звон",
    )
)


@dataclass
class Analysis:
    kind: AnalysisKind
    facts: dict[str, str] = field(default_factory=dict)
    user_question: str | None = None
    answer_type: AnswerType | None = None
    refusal_slot: SlotName | None = None
    safety_reason: str | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "facts": dict(self.facts),
            "user_question": self.user_question,
            "answer_type": self.answer_type.value if self.answer_type else None,
            "refusal_slot": self.refusal_slot.value if self.refusal_slot else None,
            "safety_reason": self.safety_reason,
            "confidence": self.confidence,
        }


def _matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(p.search(text) for p in patterns)


def _is_correction_turn(text: str) -> bool:
    if _matches_any(text, CORRECTION_PATTERNS):
        return True
    low = text.lower()
    if re.search(r"\bне\s+\w+\b", low) and extract_correction_symptom(text) is not None:
        return True
    return False


def classify_user_question(text: str) -> AnswerType:
    """Subtype for DIRECT_USER_QUESTION — analyzer only."""
    low = (text or "").lower()
    if _matches_any(low, WHY_CALLING_PATTERNS):
        return AnswerType.WHY_CALLING
    if _matches_any(low, IDENTITY_PATTERNS):
        return AnswerType.IDENTITY
    if _matches_any(low, PRIVACY_PATTERNS):
        return AnswerType.PRIVACY
    return AnswerType.OTHER


def _detect_refusal_slot(text: str, state: ConversationState) -> SlotName | None:
    explicit = slot_from_text(text)
    if explicit is not None and is_refusal(text, explicit):
        return explicit
    if state.pending_slot is not None and is_refusal(text, state.pending_slot):
        return state.pending_slot
    if is_refusal(text):
        return state.pending_slot or state.current_topic
    return None


def _build_normal_facts(text: str, state: ConversationState) -> dict[str, str]:
    facts: dict[str, str] = {}
    symptom = extract_symptom_code(text)
    if symptom:
        facts["symptom"] = symptom

    answered = detect_slot_answer(text, state.pending_slot)
    if answered is not None:
        facts["answered_slot"] = answered.value

    low = text.lower()
    if "помогло" in low or "легче" in low or ("лучше" in low and "стало" in low):
        facts["improvement"] = "yes"
    if "противореч" in low or ("нет" in low and state.facts.get("symptom")):
        facts["contradiction"] = "possible"
    return facts


def analyze_turn(text: str, state: ConversationState) -> Analysis:
    """Classify user message — does not choose assistant phrasing."""
    raw = (text or "").strip()
    if not raw:
        return Analysis(kind=AnalysisKind.NORMAL_RESPONSE)

    low = raw.lower()

    if _matches_any(low, SAFETY_PATTERNS):
        reason = "distress_signal"
        for pat in SAFETY_PATTERNS:
            if pat.search(low):
                reason = pat.pattern
                break
        facts = {"safety": "alert"}
        symptom = extract_symptom_code(raw)
        if symptom:
            facts["symptom"] = symptom
        return Analysis(
            kind=AnalysisKind.SAFETY,
            facts=facts,
            safety_reason=reason,
        )

    if is_user_fatigue(raw):
        return Analysis(
            kind=AnalysisKind.USER_FATIGUE,
            facts={"user_fatigue": "yes"},
        )

    if is_wait_request(raw):
        return Analysis(
            kind=AnalysisKind.WAIT_REQUEST,
            facts={"wait_request": "yes"},
        )

    if _matches_any(low, REPAIR_PATTERNS):
        return Analysis(kind=AnalysisKind.REPAIR)

    if _is_correction_turn(raw):
        facts = {}
        symptom = extract_correction_symptom(raw)
        if symptom:
            facts["symptom"] = symptom
        return Analysis(kind=AnalysisKind.CORRECTION, facts=facts)

    refusal_slot = _detect_refusal_slot(raw, state)
    if refusal_slot is not None:
        return Analysis(
            kind=AnalysisKind.TOPIC_REFUSAL,
            refusal_slot=refusal_slot,
            facts={"refused_slot": refusal_slot.value},
        )

    if _matches_any(low, GOODBYE_PATTERNS):
        return Analysis(kind=AnalysisKind.GOODBYE)

    if _matches_any(low, QUESTION_PATTERNS) or "?" in raw:
        facts: dict[str, str] = {}
        answer_type = classify_user_question(raw)
        if answer_type == AnswerType.PRIVACY:
            facts["privacy"] = "requested"
        return Analysis(
            kind=AnalysisKind.DIRECT_USER_QUESTION,
            user_question=raw,
            answer_type=answer_type,
            facts=facts,
        )

    return Analysis(
        kind=AnalysisKind.NORMAL_RESPONSE,
        facts=_build_normal_facts(raw, state),
    )
