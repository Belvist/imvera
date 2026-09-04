"""Output guards — every string to TTS passes through here."""
from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional

MINIMAL_FALLBACK = "Простите, не расслышала. Как вы себя чувствуете?"

_SELF_FEM = {
    "рад": "рада", "был": "была", "сделал": "сделала", "готов": "готова",
    "услышал": "услышала", "записал": "записала", "понял": "поняла",
    "передал": "передала", "проверил": "проверила", "помог": "помогла",
    "успел": "успела", "смог": "смогла", "заметил": "заметила",
    "запомнил": "запомнила", "прав": "права", "согласен": "согласна",
    "доволен": "довольна", "занят": "занята", "должен": "должна",
}

_MIRROR_OPENERS_RE = re.compile(
    r"^\s*(вы говорите|вы слышали|вы сказали|вы сомневаетесь|"
    r"вы спрашиваете|как приятно,?\s+что вы|рад[аы]?,?\s+что вы "
    r"(хорошо|нормально))", re.I)
_LATIN_WORD_RE = re.compile(r"[A-Za-z]")
_ACTION_PROMISE_RE = re.compile(
    r"\b(позвоню|вызову|отправлю|предупрежу|передам|организую|"
    r"закажу|сообщу|напишу)\b", re.I)
_HALLUCINATION_RE = re.compile(
    r"выглядите|выглядишь|голос (хорош|звучит)|какой у вас голос", re.I)
_WRONG_NEG_RE = re.compile(
    r"извините.*(?:не\s+(?:очень\s+)?хорош|плохо)|"
    r"жаль\s+.*(?:не\s+(?:очень\s+)?хорош|плохо)|"
    r"сочувствую.*(?:настроен|самочувств)",
    re.I)
_WELLNESS_IN_TRANSCRIPT_RE = re.compile(
    r"норм|хорош|пойд[её]т|не\s+плох|легче|лучше", re.I)
_RESCUE_FRAMING_RE = re.compile(
    r"(дождитесь\s+помощ|скорую|скорой|вызов\w*\s+скор|"
    r"помощь\s+уже\s+едет|скоро\s+приедут|я\s+вызову)",
    re.I)
_MEDICAL_ADVICE_RE = re.compile(
    r"(примите\s+(?:таблетк|лекарств)|увелич(ь|ьте)\s+доз|"
    r"отмен(ите|яйте)\s+лекарств|самолечени|диагноз)",
    re.I)

SAFE_ACKS = (
    "Спасибо. Как вы себя чувствуете?",
    "Понятно. Как настроение?",
    "Спасибо. Как вы поживаете?",
)

_FALSE_HEARING_RE = re.compile(
    r"\b(услышал\w*|записал\w*|разобрал\w*|понял\w*|слышу\s+вас)\b",
    re.I,
)
_POSITIVE_ON_BAD_RE = re.compile(
    r"как\s+приятно|рада\s+это\s+слышать|как\s+хорошо|"
    r"как\s+радостно|с\s+удовольствием\s+послушал",
    re.I,
)
_UNCLEAR_INPUT_REASONS = frozenset((
    "echo", "off_agenda", "low_conf", "stt_uncertain", "empty",
))

_REPEAT_STOP = frozenset(
    "и в а на с по к у о из за от для что как не да нет это я вы "
    "она он они мы вы".split()
)


def _normalize_reply(text: str) -> str:
    low = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return " ".join(w for w in low.split() if w and w not in _REPEAT_STOP)


def reply_too_similar(a: str, b: str, *, threshold: float = 0.62) -> bool:
    if not a or not b:
        return False
    na, nb = _normalize_reply(a), _normalize_reply(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(len(ta), len(tb))
    return overlap >= threshold


def same_topic_question(
    a: str,
    b: str,
    topic: str = "",
    *,
    topic_keys: Optional[Dict[str, Any]] = None,
) -> bool:
    if not a or not b or "?" not in a or "?" not in b:
        return False
    if reply_too_similar(a, b, threshold=0.45):
        return True
    keys_map = topic_keys or {}
    keys = keys_map.get((topic or "").strip().lower(), ())
    la, lb = a.lower(), b.lower()
    if keys and "?" in a and "?" in b:
        a_keys = {k for k in keys if k in la}
        b_keys = {k for k in keys if k in lb}
        if a_keys and b_keys and a_keys & b_keys:
            return True
    if not keys:
        keys = tuple(k for ks in keys_map.values() for k in ks)
    for k in keys:
        if k in la and k in lb:
            return True
    return False


def reply_looks_wrong_sentiment(reply: str, transcript: str) -> bool:
    if not reply or not transcript:
        return False
    if not _WRONG_NEG_RE.search(reply):
        return False
    low = transcript.lower()
    if any(w in low for w in ("плох", "болит", "боль", "не очень")):
        return False
    return bool(_WELLNESS_IN_TRANSCRIPT_RE.search(low))


def feminize_self(sentence: str) -> str:
    sentence = re.sub(r"^(\s*)Понял(\b)", r"\1Поняла\2", sentence,
                      flags=re.IGNORECASE)
    out, seen_ya = [], False
    for w in sentence.split():
        m = re.match(r"^(.*?)([,.!?…:;]*)$", w)
        core, punct = m.group(1), m.group(2)
        lw = core.lower()
        if lw == "я":
            seen_ya = True
            out.append(w)
            continue
        fem = _SELF_FEM.get(lw)
        if seen_ya and fem and fem != lw:
            if core[:1].isupper():
                fem = fem.capitalize()
            w = fem + punct
        out.append(w)
    return " ".join(out)


def trim_to_single_question(text: str) -> str:
    t = " ".join((text or "").split())
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+", t) if s.strip()]
    q_seen = False
    kept = []
    for s in sentences:
        if "?" in s:
            if q_seen:
                break
            q_seen = True
        kept.append(feminize_self(s))
    return " ".join(kept).strip() or t


def reply_looks_broken(reply: str) -> bool:
    if not reply:
        return False
    if _MIRROR_OPENERS_RE.match(reply):
        return True
    if _ACTION_PROMISE_RE.search(reply):
        return True
    low = reply.lower()
    if re.match(r"^\s*понятно\s*[,.\-–—]", low) and "?" not in reply:
        if not re.search(
            r"\b(как|что|где|когда|чем|расскаж|скаж|есть\s+ли|была\s+ли)\b",
            low,
        ):
            return True
    if re.search(r"давай(те)?\s*,?\s*пока", low) \
            and "до свидания" not in low and "всего доброго" not in low:
        return True
    letters = _LATIN_WORD_RE.findall(reply)
    return len(letters) >= 4


def reply_looks_hallucinated(reply: str, transcript: str) -> bool:
    if not reply:
        return False
    if _HALLUCINATION_RE.search(reply):
        return True
    m = re.search(
        r"вы (хорошо )?(выглядите|себя чувствуете сегодня отлично)",
        reply,
        re.I,
    )
    return bool(m) and "чувствует" not in (transcript or "").lower()


def looks_like_rescue_framing(reply: str) -> bool:
    return bool(reply and _RESCUE_FRAMING_RE.search(reply))


def looks_like_medical_advice(reply: str) -> bool:
    return bool(reply and _MEDICAL_ADVICE_RE.search(reply))


def reply_falsely_claims_hearing(reply: str, input_reason: str) -> bool:
    """Block «услышала/записала» when the turn was empty or rejected."""
    if (input_reason or "") not in _UNCLEAR_INPUT_REASONS:
        return False
    return bool(_FALSE_HEARING_RE.search(reply or ""))


def reply_contradicts_bad_wellness(reply: str, wellness_band: str) -> bool:
    """Positive warmth on BAD/MEDIUM/CRITICAL band — live call e804 regression."""
    band = (wellness_band or "").strip().lower()
    if band not in ("bad", "medium", "critical"):
        return False
    text = (reply or "").strip()
    if not text:
        return False
    if _POSITIVE_ON_BAD_RE.search(text):
        return True
    low = text.lower()
    if "спасибо" in low and not re.search(
            r"жал|беспоко|болит|нехорош|плох", low):
        if re.search(r"чувствуете|настроение|поживаете|самочувств", low):
            return True
    return False


def _pick_safe_ack() -> str:
    return random.choice(SAFE_ACKS)


def _replacement(fallback: str) -> str:
    fb = (fallback or "").strip()
    if fb and not reply_looks_broken(fb) \
            and not looks_like_rescue_framing(fb) \
            and not looks_like_medical_advice(fb):
        return fb
    return _pick_safe_ack()


def sanitize_segment(
    segment: str,
    *,
    fallback: str = "",
    transcript: str = "",
    llm_generated: bool = False,
    clean_llm=None,
) -> str:
    if not segment:
        return segment
    if llm_generated:
        if reply_looks_hallucinated(segment, transcript) \
                or reply_looks_broken(segment) \
                or reply_looks_wrong_sentiment(segment, transcript):
            return _replacement(fallback)
        if clean_llm is not None:
            cleaned = clean_llm(segment)
            if cleaned:
                segment = cleaned
    if reply_looks_broken(segment) or looks_like_rescue_framing(segment) \
            or looks_like_medical_advice(segment):
        return _replacement(fallback)
    return segment


def sanitize_reply(text: str, *, fallback: str = "") -> str:
    if not text:
        return fallback or MINIMAL_FALLBACK
    cleaned = trim_to_single_question(text)
    if reply_looks_broken(cleaned) or looks_like_rescue_framing(cleaned) \
            or looks_like_medical_advice(cleaned):
        fb = (fallback or "").strip()
        if fb and not reply_looks_broken(fb):
            return trim_to_single_question(fb)
        return MINIMAL_FALLBACK
    return cleaned
