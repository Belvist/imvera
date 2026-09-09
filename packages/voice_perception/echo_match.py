"""Candidate-specific echo text match — metrics never cross bot phrases."""

from __future__ import annotations

from dataclasses import dataclass

from packages.voice_perception.text_echo import compute_text_similarity


@dataclass(frozen=True)
class EchoTextMatch:
    candidate_generation_id: str
    candidate_text: str
    candidate_intent: str
    exact_match: bool
    user_coverage: float
    bot_coverage: float
    jaccard: float
    ordered_similarity: float

    @property
    def unified_score(self) -> float:
        """Single score for candidate ranking — all metrics from the same phrase."""
        if self.exact_match:
            return 1.0
        return max(
            self.user_coverage,
            self.bot_coverage,
            self.jaccard,
            self.ordered_similarity,
        )

    def as_dict(self) -> dict[str, float | bool | str]:
        return {
            "candidate_generation_id": self.candidate_generation_id,
            "candidate_text": self.candidate_text,
            "candidate_intent": self.candidate_intent,
            "exact_match": self.exact_match,
            "user_coverage": self.user_coverage,
            "bot_coverage": self.bot_coverage,
            "jaccard": self.jaccard,
            "ordered_similarity": self.ordered_similarity,
            "unified_score": round(self.unified_score, 3),
        }


def _match_for_phrase(
    user_text: str,
    phrase: str,
    *,
    generation_id: str = "",
    intent: str = "",
) -> EchoTextMatch:
    metrics = compute_text_similarity(user_text, phrase)
    return EchoTextMatch(
        candidate_generation_id=generation_id,
        candidate_text=phrase,
        candidate_intent=intent,
        exact_match=bool(metrics.get("exact_match")),
        user_coverage=float(metrics.get("user_coverage", 0)),
        bot_coverage=float(metrics.get("bot_coverage", 0)),
        jaccard=float(metrics.get("jaccard", 0)),
        ordered_similarity=float(metrics.get("ordered_similarity", 0)),
    )


def best_echo_text_match(
    user_text: str,
    bot_candidates: tuple[str, ...],
    *,
    primary_bot: str = "",
    generation_ids: tuple[str, ...] = (),
    intents: tuple[str, ...] = (),
) -> EchoTextMatch | None:
    """Pick one best candidate; all downstream echo logic uses this object only."""
    refs: list[tuple[str, str, str]] = []
    if primary_bot:
        gid = generation_ids[0] if generation_ids else ""
        intent = intents[0] if intents else ""
        refs.append((primary_bot, gid, intent))
    for idx, phrase in enumerate(bot_candidates):
        if phrase and phrase not in {r[0] for r in refs}:
            gid = generation_ids[idx] if idx < len(generation_ids) else ""
            intent = intents[idx] if idx < len(intents) else ""
            refs.append((phrase, gid, intent))
    if not refs:
        return None
    matches = [
        _match_for_phrase(user_text, phrase, generation_id=gid, intent=intent)
        for phrase, gid, intent in refs
    ]
    return max(matches, key=lambda m: m.unified_score)
