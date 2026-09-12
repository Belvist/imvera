"""Frozen issue-family plans — product contract (MVP-aligned)."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.dialogue_engine.state import IssueEpisode

# Hard product caps: MVP headache is 3 steps (when + severity + associated).
MAX_ASKS_PER_FAMILY = 3
MAX_CONTENT_ASKS_PER_CALL = 6

ASSOCIATED_LABELS = frozenset(
    {"тошнота", "тошнит", "головокружение", "слабость", "усталость"}
)


class ProductFamily(StrEnum):
    HEADACHE = "headache"
    ABDOMINAL = "abdominal"
    LIMB_PAIN = "limb_pain"
    WEAKNESS = "weakness"
    DIZZINESS = "dizziness"
    SLEEP = "sleep"
    NUTRITION = "nutrition"
    MOOD = "mood"
    MEDICATION = "medication"
    OTHER = "other"


# Ordered dimensions to ask (skip when already known / unknown / resolved).
# MVP headache: onset/duration → severity_trend → associated (nausea/etc.).
FAMILY_PLANS: dict[ProductFamily, tuple[str, ...]] = {
    ProductFamily.HEADACHE: ("duration", "severity", "associated"),
    ProductFamily.ABDOMINAL: ("onset", "current"),
    ProductFamily.LIMB_PAIN: ("onset", "severity"),
    ProductFamily.WEAKNESS: ("onset", "severity"),
    ProductFamily.DIZZINESS: ("current", "severity"),
    ProductFamily.SLEEP: ("pattern", "daytime_impact"),
    ProductFamily.NUTRITION: ("intake", "barrier"),
    ProductFamily.MOOD: ("intensity", "social_context"),
    ProductFamily.MEDICATION: ("status_today",),
    ProductFamily.OTHER: ("needs_help",),
}


def plan_steps_for_family(
    family: ProductFamily,
    *,
    call_has_temporal: bool = False,
) -> tuple[str, ...]:
    steps = FAMILY_PLANS.get(family, FAMILY_PLANS[ProductFamily.OTHER])
    # After we already asked «когда началось» for another issue in this call,
    # do not re-ask onset for abdomen — go straight to «а сейчас».
    if family == ProductFamily.ABDOMINAL and call_has_temporal:
        return ("current",)
    return steps


def call_has_temporal_answer(state: object) -> bool:
    """True when any episode already has onset/duration from this call."""
    from packages.dialogue_engine.product.known import call_has_temporal_answer as _known

    return _known(state)  # type: ignore[arg-type]


def classify_episode_family(ep: IssueEpisode) -> ProductFamily:
    """Map generic IssueEpisode → product family (deterministic)."""
    label = (ep.primary_label or "").lower()
    site = (ep.body_site or "").lower()
    kind = (ep.kind or "").lower()

    if kind == "sleep_problem" or any(x in label for x in ("спал", "сон", "бессон")):
        return ProductFamily.SLEEP
    if site == "голова" or "голов" in label:
        if any(x in label for x in ("круж", "головокруж")):
            return ProductFamily.DIZZINESS
        return ProductFamily.HEADACHE
    if site == "живот" or "живот" in label:
        return ProductFamily.ABDOMINAL
    if any(x in label for x in ("круж", "головокруж")) or site in {"головокружение"}:
        return ProductFamily.DIZZINESS
    if any(x in label for x in ("слаб",)):
        return ProductFamily.WEAKNESS
    if site in {"рука", "нога", "колено", "спина", "шея", "сустав"} or any(
        x in label for x in ("рука", "нога", "колен", "спин", "сустав", "ломит")
    ):
        return ProductFamily.LIMB_PAIN
    if any(x in label for x in ("таблет", "лекар", "препарат")):
        return ProductFamily.MEDICATION
    if any(x in label for x in ("ел", "ела", "пил", "пила", "аппетит", "голод", "есть")):
        return ProductFamily.NUTRITION
    if any(x in label for x in ("груст", "одинок", "тревож", "настроен")):
        return ProductFamily.MOOD
    if kind == "other":
        return ProductFamily.OTHER
    return ProductFamily.OTHER
