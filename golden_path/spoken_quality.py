"""Lightweight FINAL spoken-output quality checks (not full grammar FSM)."""
from __future__ import annotations

import re

# Brand names allowed in Latin script.
_LATIN_WHITELIST: frozenset[str] = frozenset({"imvera"})

# Internal enum / fact keys that must never appear in spoken output.
_INTERNAL_LEAK_RE = re.compile(
    r"\b("
    r"knee|head|back|abdomen|leg|arm|heart|pressure|throat|chest|"
    r"sleep_last_night|mood_today|plans_today|wellness_now|"
    r"negative_or_mixed|positive_or_neutral|symptom=|answered_slot"
    r")\b",
    re.IGNORECASE,
)

_INSTRUCTION_LEAK_RE = re.compile(
    r"\b("
    r"попрощайтесь|поприветствуйте|спросите|скажите\s+пользователю|"
    r"ответьте\s+пользователю|объясните\s+пользователю|"
    r"переформулируйте|подтвердите\s+исправление"
    r")\b",
    re.IGNORECASE,
)

_PERCEPTION_RE = re.compile(
    r"\b(вы\s+выглядит\w*|я\s+вижу|по\s+вашему\s+виду)\b",
    re.IGNORECASE,
)

_ASSISTANT_MALE_SELF_RE = re.compile(
    r"\bя\s+(?:\w+\s+){0,2}(устал|понял|рад|записал|услышал|позвонил|отправил)\b",
    re.IGNORECASE,
)

_UNCONFIRMED_ACTION_RE = re.compile(
    r"("
    r"близкие\s+увидят|"
    r"я\s+всё\s+записала|"
    r"всё\s+записала|"
    r"я\s+передала|"
    r"я\s+оповестила|"
    r"переда\w+\s+близк\w*"
    r")",
    re.IGNORECASE,
)

_USER_GENDER_SLEEP_RE = re.compile(
    r"\b(как\s+прошл\w*\s+ночь\s+спал\b|"
    r"вы\s+спал\b|"
    r"вы\s+устал\w*\b|"
    r"вы\s+выглядит\w*\s+устав\w*\b|"
    r"\bуставшим\b)",
    re.IGNORECASE,
)

_LATIN_WORD_RE = re.compile(r"\b[a-z]{3,}\b", re.IGNORECASE)

# Permanent regression corpus — these FINAL phrases must never pass.
KNOWN_BAD_FINALS: frozenset[str] = frozenset(
    s.lower()
    for s in (
        "Вы спали хорошо last night?",
        "Попрощайтесь, ничего не планируете.",
        "Хорошо, перейдём к другому теме. Что вас интересует?",
        "Что вас интересует?",
        "Вы говорите, что симптом — это спину?",
        "Сон был сегодня?",
        "Как прошлую ночь спал?",
        "Вы говорили о среднем.",
        "Вы мне очень помогли, но я уже устал.",
        "Вы выглядите уставшим.",
        "Вы говорите, что симптом — это спинка?",
        "Вы уверены, что симптом — это колено?",
        "Вы хотите подтвердить исправление симптома «кnee»?",
        "Вам нужно узнать, как вы чувствуетесь.",
        "Хорошо, мы говорили долго. Поприветствуйте её.",
        "Прощай, до встречи.",
    )
)


def check_spoken_quality(text: str) -> list[str]:
    """Return spoken-quality violation codes (empty = OK)."""
    violations: list[str] = []
    candidate = (text or "").strip()
    if not candidate:
        return violations

    low = candidate.lower()
    if low in KNOWN_BAD_FINALS:
        violations.append("known_bad_regression")

    for word in _LATIN_WORD_RE.findall(candidate):
        if word.lower() not in _LATIN_WHITELIST:
            violations.append("latin_in_russian")
            break

    if _INTERNAL_LEAK_RE.search(candidate):
        violations.append("internal_label_leak")

    if _INSTRUCTION_LEAK_RE.search(candidate):
        violations.append("instruction_leakage")

    if _PERCEPTION_RE.search(candidate):
        violations.append("hallucinated_perception")

    if _UNCONFIRMED_ACTION_RE.search(candidate):
        violations.append("unconfirmed_action_claim")

    if _ASSISTANT_MALE_SELF_RE.search(candidate):
        violations.append("assistant_masculine_self")

    if _USER_GENDER_SLEEP_RE.search(candidate):
        violations.append("user_gender_guess")

    # Broken correction templates
    if re.search(r"симптом\s*—\s*это\s+\w+у\??", low):
        violations.append("broken_correction_grammar")
    if "симптом" in low and "?" in candidate and "поняла" not in low:
        violations.append("correction_as_question")

    return violations
