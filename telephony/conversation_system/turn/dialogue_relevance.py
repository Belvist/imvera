"""Detect when STT captured background media or speech not aimed at Vera.

Phone recordings are mono-mixed: Vera's playback, room TV/YouTube, and the
caller may all land in one WAV. Vocabulary gates pass video dialogue because
it is fluent Russian. This module rejects off-agenda monologues before the
dialogue engine treats them as «как приятно, расскажите ещё».
"""
from __future__ import annotations

import re

from conversation_system.turn._classifiers import (
    is_closing,
    is_greeting,
    is_help_request,
    is_meta_confusion,
    is_refusal,
    is_repair,
    is_text_question,
)
from conversation_system.turn._cleaners import wellness_short_answer
from core.vocab import (
    contains_health_signal,
    looks_like_directed_caller_speech,
    looks_like_stt_glue_noise,
)

# Streaming / social / meme dialogue — never a care-call answer.
_MEDIA_BLEED_MARKERS: tuple[str, ...] = (
    "видео", "ютуб", "you tube", "тикток", "tiktok", "ролик", "клип",
    "подпис", "лайк", "стрим", "блогер", "трек", "рэп", "репчик",
    "индейк", "макарон", "стейк", "залайк", "просмотр", "переслал",
    "мем", "прикол", "дамураш", "damur", "круто снят",
    "смотрите", "слушайте", "ставьте", "нажмите", "переходите",
    "подкаст", "выпуск", "эпизод", "трансляц", "репост",
)

_AUDIENCE_IMPERATIVE_RE = re.compile(
    r"\b(смотрите|слушайте|подписывайтесь|ставьте|нажмите|переходите|"
    r"лайкайте|делитесь|комментируйте)\b",
    re.IGNORECASE,
)
_INFORMAL_YOU_RE = re.compile(
    r"\b(тебя|тебе|ты)\b",
    re.IGNORECASE,
)
_PROFANITY_BLEED_RE = re.compile(
    r"\b(сука|суки|бля|блять|нахуй|пизд|хуй|ёб|еба|ебан|кикули|дерьм)\b",
    re.IGNORECASE,
)
_OVERHEARD_NO_I_RE = re.compile(
    r"\b(я|мне|меня|мой|моя|мои|мы|нам|нас|вы|вам|ваш|ваша|ваши)\b",
    re.IGNORECASE,
)

_CARE_QUESTION_HINTS: tuple[str, ...] = (
    "чувству", "пожива", "настроени", "сон", "спал", "спала", "выспал",
    "самочувств", "здоров", "болит", "беспоко", "как вы", "как вы сегодня",
    "хорошо или плохо", "терпим", "сильн",
)

_CARE_ANSWER_HINTS: tuple[str, ...] = (
    "чувств", "настроени", "сон", "спал", "спала", "выспал", "бессон",
    "устал", "устала", "болит", "болело", "голов", "мигрен", "давлен", "таблет",
    "лекар", "план", "гуля", "внук", "внучк", "родн", "семь", "хорош",
    "плох", "нормал", "терпим", "легче", "лучше", "помог", "принял",
    "приняла", "завтрак", "обед", "ужин",
)


def last_question_expects_care_answer(last_question: str) -> bool:
    lq = (last_question or "").strip().lower()
    if not lq:
        return False
    return any(h in lq for h in _CARE_QUESTION_HINTS)


def looks_like_media_bleed(text: str) -> bool:
    """True when transcript looks like TV/YouTube/social clip, not a phone call."""
    low = (text or "").strip().lower()
    if not low:
        return False
    if any(m in low for m in _MEDIA_BLEED_MARKERS):
        return True
    if _AUDIENCE_IMPERATIVE_RE.search(low):
        return True
    if re.search(r"\b(пацаны|ребят[аи]?|братан|парни|жесть|ахуе)\b", low):
        return True
    return False


def looks_like_overheard_speech(text: str) -> bool:
    """Room/TV monologue with no care content and no address to Vera."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    low = cleaned.lower()
    words = low.split()
    if len(words) < 4:
        return False
    if _plausible_care_answer(cleaned):
        return False
    if looks_like_media_bleed(cleaned):
        return True
    if not _OVERHEARD_NO_I_RE.search(low):
        return True
    if len(words) >= 8 and not _plausible_care_answer(cleaned):
        return True
    return False


def looks_like_hostile_or_unintelligible_bleed(text: str) -> bool:
    """Profanity or informal «ты» rant — typical TV/background, not the elder."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    low = cleaned.lower()
    if _PROFANITY_BLEED_RE.search(low):
        return True
    if _INFORMAL_YOU_RE.search(low) and len(low.split()) >= 5:
        if not _plausible_care_answer(cleaned):
            return True
    return False


def is_explicit_caller_turn(text: str) -> bool:
    """Caller speech that must reach intent and safety classification.

    Mixed phone audio is ambiguous.  For explicit questions, repair/control
    requests, and health signals, a false rejection is more harmful than an
    occasional background false positive.  SafetyEngine and IntentResolver
    still apply their subject-aware policies after this preservation gate.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if contains_health_signal(cleaned):
        return True
    if looks_like_directed_caller_speech(cleaned):
        return True
    return any((
        is_greeting(cleaned),
        is_closing(cleaned),
        is_refusal(cleaned),
        is_repair(cleaned),
        is_meta_confusion(cleaned),
        is_help_request(cleaned),
        is_text_question(cleaned),
    ))


def _plausible_care_answer(text: str) -> bool:
    if wellness_short_answer(text):
        return True
    if is_explicit_caller_turn(text):
        return True
    low = text.lower()
    return any(h in low for h in _CARE_ANSWER_HINTS)


def is_off_agenda_for_care_question(text: str, last_question: str) -> bool:
    """Long speech that is not an answer to Vera's wellness/agenda question."""
    cleaned = (text or "").strip()
    if not cleaned or not last_question_expects_care_answer(last_question):
        return False
    if looks_like_media_bleed(cleaned):
        return True
    if len(cleaned.split()) < 4:
        return False
    if _plausible_care_answer(cleaned):
        return False
    return True


def should_reject_mixed_capture(
    text: str,
    *,
    last_question: str = "",
) -> bool:
    """Reject transcript before dialogue when it is not caller→Vera speech."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    # Intentional caller control and safety content take precedence over the
    # statistical background heuristics below.  Previously this check came
    # too late, so questions, repairs and even «я упал и не могу встать» were
    # converted to OFF_AGENDA before SafetyEngine could inspect them.
    if is_explicit_caller_turn(cleaned):
        return False
    if looks_like_media_bleed(cleaned):
        return True
    if looks_like_stt_glue_noise(cleaned):
        return True
    if looks_like_hostile_or_unintelligible_bleed(cleaned):
        return True
    if last_question_expects_care_answer(last_question):
        if looks_like_overheard_speech(cleaned):
            return True
        if last_question and is_off_agenda_for_care_question(cleaned, last_question):
            return True
    elif last_question and is_off_agenda_for_care_question(cleaned, last_question):
        return True
    return False
