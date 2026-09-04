"""Deterministic turn parser — one immutable TurnUnderstanding per turn."""
from __future__ import annotations

import re
from typing import Sequence

from conversation_system.agenda.topics import (
    BAD_WORDS,
    BODY_FOCUS_PATTERNS,
    OK_WORDS,
    TOPIC_KEYS,
    TOPIC_WELLNESS,
)
from conversation_system.domain.wellness import WellnessBand, classify_wellness
from conversation_system.domain.understanding import (
    ConfidenceBand,
    SpeechAct,
    SttReason,
    TurnUnderstanding,
)
from conversation_system.turn._classifiers import (
    is_ack,
    is_closing,
    is_closing_direct,
    is_greeting,
    is_help_request,
    is_meta_confusion,
    is_refusal,
    is_repair,
    is_text_question,
    is_worry,
)
from conversation_system.turn._cleaners import (
    clean_transcript,
    short_real_answer,
    wellness_short_answer,
)
from conversation_system.turn.dialogue_relevance import (
    looks_like_media_bleed,
    should_reject_mixed_capture,
)
from core.safety_engine import SafetyEngine


def _normalize_stt_reason(reason: str | None) -> SttReason:
    raw = (reason or "").strip().lower()
    mapping = {
        "": SttReason.NONE,
        "empty": SttReason.EMPTY,
        "low_conf": SttReason.LOW_CONF,
        "echo": SttReason.ECHO,
        "off_agenda": SttReason.OFF_AGENDA,
        "stt_uncertain": SttReason.STT_UNCERTAIN,
    }
    return mapping.get(raw, SttReason.NONE)


def _confidence_band(confidence: float | None) -> ConfidenceBand:
    if confidence is None:
        return ConfidenceBand.MEDIUM
    if confidence >= 0.8:
        return ConfidenceBand.HIGH
    if confidence >= 0.55:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def extract_symptom_focus(text: str) -> str:
    """First body-part mention — use extract_correction_focus for corrections."""
    _superseded, new_focus = extract_correction_focus(text)
    if new_focus:
        return new_focus
    low = (text or "").lower()
    for pattern, label in BODY_FOCUS_PATTERNS:
        if re.search(pattern, low):
            return label
    return ""


def extract_correction_focus(text: str) -> tuple[str, str]:
    """
    Parse correction utterances: (superseded_label, new_active_label).

    Example: «нет, не голова, я ошиблась — спина болит» → («голова», «спина»).
    """
    low = (text or "").lower()
    if not low.strip():
        return "", ""

    superseded = ""
    for pattern, label in BODY_FOCUS_PATTERNS:
        if re.search(rf"(?:^|[\s,])не\s+(?:{pattern}|{re.escape(label)})", low):
            superseded = label
            break
        if re.search(rf"не\s+{label}\b", low):
            superseded = label
            break

    split_markers = re.split(
        r"[—\-]|(?:\s+а\s+)|(?:ошиб\w*)|(?:имел\w*\s+в\s+виду)|(?:имела\w*\s+в\s+виду)",
        low,
    )
    search_segments = split_markers if len(split_markers) > 1 else [low]

    new_focus = ""
    for segment in reversed(search_segments):
        for pattern, label in BODY_FOCUS_PATTERNS:
            if re.search(pattern, segment) and label != superseded:
                new_focus = label
                break
        if new_focus:
            break

    if not new_focus:
        mentions: list[str] = []
        for pattern, label in BODY_FOCUS_PATTERNS:
            if re.search(pattern, low):
                mentions.append(label)
        for label in reversed(mentions):
            if label != superseded:
                new_focus = label
                break

    return superseded, new_focus


def mentions_symptom(text: str) -> bool:
    if not (text or "").strip():
        return False
    low = text.lower()
    if re.search(r"ничего\s+(?:сегодня\s+)?не\s+бол", low):
        return False
    if re.search(r"\bне\s+бол(?:ит|ел|ела|еет)\b", low) \
            and re.search(r"хорош|нормал|отлич", low):
        return False
    return bool(re.search(
        r"голов|мигрен|болит|болел|болела|болеет|тошн|ташн|круж|давлен|"
        r"температур|слабост|недомог|ноет|колет|шумит|"
        r"сердц|дыш|кашл", low))


def symptom_resolved(text: str, *, clearing: bool = False) -> bool:
    if not (text or "").strip():
        return False
    low = text.lower()
    if clearing and short_real_answer(text) \
            and len(text.split()) <= 2 \
            and not re.search(
                r"(легче|лучше|хорош|нормал|стало|менее|не\s+бол)", low):
        return False
    if re.search(r"ничего\s+(?:сегодня\s+)?не\s+бол", low):
        return True
    if re.search(r"сейчас\s+(?:вс[её]|уже|очень)?\s*хорош", low):
        return True
    if re.search(r"настроени[ея].*нормал", low):
        return True
    if re.search(r"более[\s-]*мен", low):
        return clearing is False
    if re.search(
            r"\b(легче|лучше|помогло|отпустило|прошл[ао]?|"
            r"стало|улучшил|снизил|перестало)\b", low):
        return True
    if any(w in low for w in OK_WORDS) \
            and not any(w in low for w in BAD_WORDS) \
            and re.search(r"\b(сейчас|уже|отпустило|стало)\b", low):
        return True
    return False


def matches_topic(text: str, topic: str) -> bool:
    if not topic or not text:
        return False
    keys = TOPIC_KEYS.get(topic)
    if not keys:
        return False
    from conversation_system.agenda.topics import GENERIC_AGENDA_MATCH_KEYS

    low = text.lower()
    if len(text.split()) >= 6:
        specific = [k for k in keys if k not in GENERIC_AGENDA_MATCH_KEYS]
        if specific and any(k in low for k in specific):
            return True
        return False
    return any(k in low for k in keys)


def topic_signals_for(text: str) -> tuple[str, ...]:
    low = (text or "").lower()
    hits = [name for name, keys in TOPIC_KEYS.items() if any(k in low for k in keys)]
    return tuple(hits)


def answers_wellness(text: str) -> bool:
    if not (text or "").strip():
        return False
    if wellness_short_answer(text):
        return True
    low = text.lower()
    if any(w in low for w in OK_WORDS) or any(w in low for w in BAD_WORDS):
        return True
    return matches_topic(text, "самочувствие")


def is_narrative(
    text: str,
    *,
    current_topic: str = "",
    on_table: bool = False,
    last_question: str = "",
) -> bool:
    if len((text or "").split()) < 6:
        return False
    if looks_like_media_bleed(text):
        return False
    if last_question and should_reject_mixed_capture(
            text, last_question=last_question):
        return False
    if current_topic == "вопрос от родных":
        return False
    # Complaints / wellness answers are never «off-topic story».
    band = classify_wellness(text)
    if band in (WellnessBand.BAD, WellnessBand.MEDIUM, WellnessBand.CRITICAL):
        return False
    if any(w in (text or "").lower() for w in BAD_WORDS):
        return False
    if mentions_symptom(text):
        return False
    if matches_topic(text, current_topic):
        return False
    if matches_topic(text, TOPIC_WELLNESS):
        return False
    if on_table and answers_wellness(text) and len(text.split()) <= 4:
        return False
    if answers_wellness(text) and any(
            w in (text or "").lower() for w in ("плох", "болит", "боле", "устал")):
        return False
    # Narrative = long off-topic digression ONLY while answering an open agenda slot.
    # Without a question on the table this is just speech (wellness / clarify / repair).
    if not on_table:
        return False
    return True


class TurnAnalyzer:
    """Build TurnUnderstanding once per turn — no mutations, optional SafetyEngine."""

    def __init__(self, safety_engine: SafetyEngine | None = None) -> None:
        self._safety = safety_engine or SafetyEngine()

    def analyze(
        self,
        text: str | None,
        *,
        reason: str | None = None,
        confidence: float | None = None,
        last_question: str | None = None,
        current_topic: str = "",
        agenda_question_open: bool = False,
        clearing_symptom: bool = False,
    ) -> TurnUnderstanding:
        input_reason = _normalize_stt_reason(reason)
        raw = (text or "").strip()
        clean = clean_transcript(raw) or ""

        if input_reason in (SttReason.EMPTY, SttReason.ECHO) and not clean:
            return self._empty_understanding(raw, input_reason, confidence)

        if not clean and input_reason == SttReason.NONE:
            input_reason = SttReason.EMPTY

        if not clean:
            return self._empty_understanding(raw, input_reason, confidence)

        if input_reason not in (
                SttReason.EMPTY, SttReason.ECHO, SttReason.OFF_AGENDA):
            if should_reject_mixed_capture(
                    clean, last_question=last_question or ""):
                return self._empty_understanding(
                    raw, SttReason.OFF_AGENDA, confidence)

        if is_ack(raw):
            if last_question and (
                    agenda_question_open
                    or short_real_answer(clean or raw)):
                speech_act = self._classify_speech_act(clean)
            else:
                speech_act = SpeechAct.ACK
        else:
            speech_act = self._classify_speech_act(clean)
        focus = extract_symptom_focus(clean)
        sym = mentions_symptom(clean)
        resolved = symptom_resolved(clean, clearing=clearing_symptom)
        topic_hits = topic_signals_for(clean)
        on_table = agenda_question_open and bool(current_topic)
        narrative = is_narrative(
            clean,
            current_topic=current_topic,
            on_table=on_table,
            last_question=last_question or "",
        )
        if narrative:
            speech_act = SpeechAct.NARRATIVE

        # SafetyEngine.observe() runs once per turn in SafetyBridge.process
        # (shared engine). A second observe here corrupts _awaiting and can
        # escalate routine symptoms (e.g. «голова болит») to confirmed_red.

        answers_control: bool | None = None
        if last_question and wellness_short_answer(clean):
            answers_control = True
        elif last_question and is_refusal(clean):
            answers_control = False

        return TurnUnderstanding(
            raw_text=raw,
            clean_text=clean,
            input_reason=input_reason,
            speech_act=speech_act,
            topic_signals=topic_hits,
            symptom_focus=focus or None,
            answers_last_control=answers_control,
            confidence_band=_confidence_band(confidence),
            is_narrative=narrative,
            word_count=len(clean.split()),
            safety_event_kind="",
            mentions_symptom=sym,
            symptom_resolved=resolved,
            matches_current_topic=matches_topic(clean, current_topic),
        )

    def _empty_understanding(
        self,
        raw: str,
        input_reason: SttReason,
        confidence: float | None,
    ) -> TurnUnderstanding:
        return TurnUnderstanding(
            raw_text=raw,
            clean_text="",
            input_reason=input_reason,
            speech_act=SpeechAct.EMPTY,
            topic_signals=(),
            symptom_focus=None,
            answers_last_control=None,
            confidence_band=_confidence_band(confidence),
            is_narrative=False,
            word_count=0,
        )

    def _classify_speech_act(self, text: str) -> SpeechAct:
        if is_closing_direct(text):
            return SpeechAct.CLOSING_DIRECT
        if is_closing(text):
            return SpeechAct.CLOSING
        if is_greeting(text):
            return SpeechAct.GREETING
        if is_refusal(text):
            return SpeechAct.REFUSAL
        if is_repair(text):
            return SpeechAct.REPAIR
        if is_meta_confusion(text):
            return SpeechAct.META_CONFUSION
        if is_help_request(text):
            return SpeechAct.HELP
        if is_worry(text):
            return SpeechAct.WORRY
        if is_text_question(text):
            return SpeechAct.QUESTION
        if mentions_symptom(text):
            return SpeechAct.SYMPTOM
        if short_real_answer(text) and len(text.split()) <= 3:
            return SpeechAct.AFFIRMATION
        # Narrative is decided in analyze() with agenda context — bare length
        # heuristics here mis-label wellness complaints («плохо мне…») as story.
        return SpeechAct.CONTENT
