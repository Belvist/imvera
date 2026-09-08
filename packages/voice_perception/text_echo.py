"""Text-domain echo detection — filter Vera bleed before interpretation."""

from __future__ import annotations

import re


_REPAIR_SHORT = re.compile(
    r"^(какое|какая|какой|какие|что|как|где|когда|зачем|почему|"
    r"повторите|повтори|еще\s+раз|ещё\s+раз)(\s|$|\?)",
    re.I,
)


def is_repair_phrase(text: str) -> bool:
    normalized = normalize_speech_text(text)
    if not normalized:
        return False
    if re.match(r"^что\??$", normalized):
        return True
    if re.match(
        r"^(какое|какая|какой|какие|как|где|когда|зачем|почему|"
        r"повторите|повтори|еще\s+раз|ещё\s+раз)(\s|$|\?)$",
        normalized,
    ):
        return True
    return False


def normalize_speech_text(text: str) -> str:
    lowered = (text or "").lower().strip()
    lowered = re.sub(r"[^\w\s]", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", lowered).strip()


def text_echo_similarity(user_text: str, bot_text: str) -> float:
    """0..1 overlap between user STT and last bot phrase (text-domain echo score)."""
    user = normalize_speech_text(user_text)
    bot = normalize_speech_text(bot_text)
    if not user or not bot:
        return 0.0
    if user == bot:
        return 1.0
    user_tokens = user.split()
    bot_tokens = bot.split()
    if not user_tokens or not bot_tokens:
        return 0.0
    user_set = set(user_tokens)
    bot_set = set(bot_tokens)
    overlap = len(user_set & bot_set)
    denom = max(len(user_set), 1)
    ratio = overlap / denom
    if len(user) >= 6 and (bot in user or user in bot):
        ratio = max(ratio, 0.85)
    if bot_tokens[: len(user_tokens)] == user_tokens and (
        len(user_tokens) >= 2 or (user_tokens and len(user_tokens[0]) >= 4)
    ):
        ratio = max(ratio, 0.75)
    if re.match(r"^(как|что|какое|какая|какой)\s", user):
        for stem in ("настроени", "самочувств", "спал", "план"):
            if stem in user and stem in bot:
                ratio = max(ratio, 0.6)
    return min(1.0, round(ratio, 3))


def is_text_echo_of_bot(
    user_text: str,
    bot_text: str,
    *,
    allowlist: frozenset[str] | None = None,
) -> bool:
    """True when STT text is likely Vera's last phrase bleeding into the user segment."""
    normalized = normalize_speech_text(user_text)
    if not normalized:
        return True
    if is_repair_phrase(normalized):
        return False
    if allowlist and normalized in allowlist:
        return False
    if not (bot_text or "").strip():
        return False
    sim = text_echo_similarity(user_text, bot_text)
    if sim >= 0.55:
        return True
    if sim >= 0.40:
        if is_repair_phrase(normalized):
            return False
        if re.match(r"^(как|что|какое|какая|какой|каких)\s", normalized):
            bot_norm = normalize_speech_text(bot_text)
            for stem in (
                "настроени",
                "самочувств",
                "чувству",
                "спал",
                "план",
            ):
                if stem in normalized and stem in bot_norm:
                    return True
    return False
