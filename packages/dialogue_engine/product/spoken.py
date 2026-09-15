"""Spoken templates for product pack — warm, short, MVP-quality Russian."""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.dialogue_engine.product.issue_plans import ProductFamily

if TYPE_CHECKING:
    from packages.dialogue_engine.state import IssueEpisode

IMPORTANT_TO_SHARE_QUESTION = (
    "Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии "
    "или дома, на что мне стоит обратить внимание?"
)

# (attribute → spoken). {label} substituted from episode.primary_label.
_FAMILY_SPOKEN: dict[ProductFamily, dict[str, str]] = {
    ProductFamily.HEADACHE: {
        "duration": "Когда начала болеть голова — сегодня или раньше?",
        "onset": "Когда начала болеть голова — сегодня или раньше?",
        "current": "А сейчас голова ещё болит или уже почти прошла?",
        "severity": "Боль сильная или терпимая?",
        "associated": (
            "Кроме головной боли, сейчас есть что-то ещё необычное — "
            "сильная слабость, головокружение или тошнота?"
        ),
        "associated_nausea_known": (
            "А тошнота сейчас тоже сильно беспокоит или уже проходит?"
        ),
    },
    ProductFamily.ABDOMINAL: {
        "onset": "Когда это началось — сегодня или раньше?",
        "duration": "Когда это началось — сегодня или раньше?",
        "current": "А живот сейчас ещё беспокоит или уже стало лучше?",
        "severity": "Сейчас это сильно беспокоит или уже терпимо?",
    },
    ProductFamily.LIMB_PAIN: {
        "onset": "Когда появилась эта боль — сегодня или раньше?",
        "duration": "Когда появилась эта боль — сегодня или раньше?",
        "severity": "Сейчас боль сильнее или уже становится легче?",
        "current": "А сейчас ещё болит или уже почти прошло?",
    },
    ProductFamily.WEAKNESS: {
        "onset": "Когда появилась эта слабость — сегодня или раньше?",
        "duration": "Когда появилась эта слабость — сегодня или раньше?",
        "severity": (
            "Из-за слабости вам трудно встать, пройтись по комнате "
            "или делать обычные дела?"
        ),
        "current": "Слабость сейчас продолжается или уже прошло?",
    },
    ProductFamily.DIZZINESS: {
        "current": "Головокружение сейчас продолжается или уже прошло?",
        "severity": "Когда кружится голова, вы можете уверенно стоять и ходить?",
        "onset": "Когда это началось — сегодня или раньше?",
    },
    ProductFamily.SLEEP: {
        "pattern": "Это была одна плохая ночь или так уже несколько ночей?",
        "quality": "Как вы спали этой ночью?",
        "daytime_impact": (
            "А сейчас после этой ночи вы чувствуете себя бодро "
            "или есть заметная сонливость или слабость?"
        ),
    },
    ProductFamily.NUTRITION: {
        "intake": "Сегодня удалось хоть немного поесть и попить?",
        "barrier": "Если поесть не получается — из-за аппетита или другой причины?",
    },
    ProductFamily.MOOD: {
        "intensity": "Сегодня особенно грустно или просто немного не по себе?",
        "social_context": "Вам сейчас особенно не хватает общения или внимания близких?",
    },
    ProductFamily.MEDICATION: {
        "status_today": "Вы сегодня приняли лекарство, которое обычно должны принять?",
    },
    ProductFamily.OTHER: {
        "needs_help": (
            "С этой проблемой вы можете пока справиться сами "
            "или вам сейчас нужна помощь близких?"
        ),
    },
}

_GENERIC = {
    "onset": "Когда это началось — сегодня или раньше?",
    "duration": "Как давно это продолжается?",
    "current": "А сейчас это ещё беспокоит или уже прошло?",
    "severity": "Сейчас это сильно беспокоит или уже терпимо?",
    "needs_help": (
        "С этим сейчас нужна помощь близких или вы пока справляетесь?"
    ),
}


def spoken_question(family: ProductFamily, attribute: str, ep: IssueEpisode) -> str:
    table = _FAMILY_SPOKEN.get(family, {})
    if attribute == "associated" and family == ProductFamily.HEADACHE:
        labels = {(m.label or "").lower() for m in ep.mentions}
        if labels & {"тошнота", "тошнит"}:
            return table.get(
                "associated_nausea_known",
                table.get("associated", _GENERIC.get("current", "")),
            )
    text = table.get(attribute) or _GENERIC.get(attribute)
    if not text:
        label = (ep.primary_label or "это").strip()
        return f"Расскажите, пожалуйста, чуть подробнее про {label}."
    return text.format(label=ep.primary_label)


def intent_for(family: ProductFamily, attribute: str, episode_id: str) -> str:
    if family == ProductFamily.HEADACHE:
        return f"episode_headache_{attribute}"
    if family == ProductFamily.SLEEP and attribute in {
        "pattern",
        "quality",
        "daytime_impact",
    }:
        return f"episode_sleep_{attribute}"
    return f"episode_{episode_id}_{attribute}"
