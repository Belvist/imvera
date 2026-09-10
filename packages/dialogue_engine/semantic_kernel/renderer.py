"""Deterministic fast renderer — natural variants without generative LLM."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from packages.dialogue_engine.semantic_kernel.response_plan import ResponseAction, ResponsePlan

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState

_VARIANTS: dict[tuple[str, str | None], tuple[str, ...]] = {
    ("ask_attribute", "onset"): (
        "Поняла. А началось когда?",
        "Ясно. Давно это началось?",
        "Понимаю. С какого времени?",
    ),
    ("ask_attribute", "severity"): (
        "Поняла. А боль сейчас сильная?",
        "Ясно. Боль терпимая или сильная?",
        "Понимаю. Сейчас сильно болит?",
    ),
    ("ask_attribute", "current"): (
        "А сейчас это ещё беспокоит?",
        "Поняла. Сейчас уже лучше?",
        "Ясно. Это ещё мешает?",
    ),
    ("clarify", None): (
        "Уточните, пожалуйста, что именно сейчас беспокоит?",
        "Помогите понять: что именно вас тревожит?",
    ),
    ("answer_question", None): (
        "Я Вера, голосовой помощник сервиса Амвера. Звоню, чтобы узнать, как вы себя чувствуете.",
    ),
    ("never_silent", None): (
        "Понимаю. Расскажите, пожалуйста, чуть подробнее.",
        "Я слушаю. Продолжайте, пожалуйста.",
    ),
}


def render_plan(plan: ResponsePlan, *, state: EngineState | None = None, seed: int = 0) -> str:
    key = (plan.action.value, plan.attribute)
    variants = _VARIANTS.get(key) or _VARIANTS.get((plan.action.value, None), ())
    if not variants:
        ack = " ".join(plan.acknowledge).strip()
        if ack:
            return ack
        return "Понимаю."
    rng = random.Random(seed)
    base = rng.choice(variants)
    if plan.acknowledge and plan.action == ResponseAction.ASK_ATTRIBUTE:
        ack = plan.acknowledge[0]
        if ack and ack not in base:
            return f"{ack} {base}"
    return base
