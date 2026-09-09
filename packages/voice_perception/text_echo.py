"""Text-domain similarity metrics — signals only, not admission verdicts."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

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


def _token_sets(user: str, bot: str) -> tuple[list[str], list[str], set[str], set[str]]:
    user_tokens = user.split()
    bot_tokens = bot.split()
    return user_tokens, bot_tokens, set(user_tokens), set(bot_tokens)


def compute_text_similarity(user_text: str, bot_text: str) -> dict[str, float | bool]:
    """Multi-metric text overlap — diagnostic only, never a drop verdict."""
    user = normalize_speech_text(user_text)
    bot = normalize_speech_text(bot_text)
    if not user or not bot:
        return {
            "exact_match": False,
            "user_coverage": 0.0,
            "bot_coverage": 0.0,
            "jaccard": 0.0,
            "ordered_similarity": 0.0,
            "legacy_similarity": 0.0,
        }
    user_tokens, bot_tokens, user_set, bot_set = _token_sets(user, bot)
    overlap = len(user_set & bot_set)
    union = len(user_set | bot_set) or 1
    user_coverage = overlap / max(len(user_set), 1)
    bot_coverage = overlap / max(len(bot_set), 1)
    jaccard = overlap / union
    ordered = SequenceMatcher(None, user, bot).ratio()
    legacy = text_echo_similarity(user_text, bot_text)
    return {
        "exact_match": user == bot,
        "user_coverage": round(user_coverage, 3),
        "bot_coverage": round(bot_coverage, 3),
        "jaccard": round(jaccard, 3),
        "ordered_similarity": round(ordered, 3),
        "legacy_similarity": legacy,
    }


def text_echo_similarity(user_text: str, bot_text: str) -> float:
    """Legacy 0..1 overlap score — forensic / diagnostics only."""
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
    """Weak text-echo hint — never used alone for hard drop (see PostSTTTurnGate)."""
    normalized = normalize_speech_text(user_text)
    if not normalized:
        return True
    if is_repair_phrase(normalized):
        return False
    if allowlist and normalized in allowlist:
        return False
    if not (bot_text or "").strip():
        return False
    metrics = compute_text_similarity(user_text, bot_text)
    if metrics.get("exact_match"):
        return True
    ordered = float(metrics.get("ordered_similarity", 0))
    user_cov = float(metrics.get("user_coverage", 0))
    bot_cov = float(metrics.get("bot_coverage", 0))
    return ordered >= 0.95 and user_cov >= 0.95 and bot_cov >= 0.95
