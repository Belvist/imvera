"""Lexical pools — deterministic phrase selection per wellness category."""

from __future__ import annotations

from packages.dialogue_engine.corpus.schema import SlotAnswers, WellnessCategory

# Single-wrap only — avoids «Хорошо.,» double punctuation artifacts.

_WELLNESS_GOOD = (
    "Хорошо.",
    "Всё хорошо.",
    "Чувствую себя хорошо.",
    "Да нормально, всё хорошо.",
    "Отлично себя чувствую.",
    "Сегодня всё прекрасно.",
    "Вроде всё хорошо.",
    "Да хорошо вроде.",
    "Всё в порядке.",
    "Ничего не беспокоит.",
    "Замечательно.",
    "Прекрасно.",
    "Неплохо.",
    "Хорошо себя чувствую.",
    "Сегодня хорошо.",
    "Довольно хорошо.",
    "Хорошо, спасибо.",
    "Отлично, спасибо.",
    "Всё отлично.",
    "Хорошо так.",
)

_WELLNESS_NORMAL = (
    "Нормально.",
    "Обычно.",
    "Всё как всегда.",
    "Да нормально себя чувствую.",
    "В целом нормально.",
    "Средне, но нормально.",
    "Ничего особенного.",
    "Да всё нормально.",
    "Более-менее нормально.",
    "Обычное состояние.",
    "Ничего.",
    "Так обычно.",
    "Всё нормально.",
    "Нормально так.",
    "Обычное.",
    "Ничего нового.",
    "Так нормально.",
    "Нормально, спасибо.",
    "Обычно бывает.",
    "Нормально вроде.",
)

_WELLNESS_SO_SO = (
    "Так себе.",
    "Не очень.",
    "Средне.",
    "Сегодня так себе.",
    "Не особо хорошо.",
    "Бывает и лучше.",
    "Что-то не очень.",
    "Так, средненько.",
    "Неважно себя чувствую.",
    "Ну такое.",
    "Средненько.",
    "Не идеально.",
    "Так себе, нормально.",
    "Средне так.",
    "Не очень хорошо.",
    "Ну средне.",
    "Так себе сегодня.",
    "Средне, но терpимо.",
    "Не особо.",
    "Ну такое сегодня.",
)

_WELLNESS_OKAY = (
    "Пойдёт.",
    "Да пойдёт.",
    "Более-менее.",
    "Терpимо.",
    "Вроде пойдёт.",
    "Ничего.",
    "Жить можно.",
    "Сойдёт.",
    "В целом терpимо.",
    "Не идеально, но пойдёт.",
    "Сойдет.",
    "Пойдет.",
    "Ну пойдёт.",
    "Терпимо так.",
    "Сойдёт пока.",
    "Пойдёт так.",
    "Ну сойдёт.",
    "Более-менее нормально.",
    "Пойдёт на сегодня.",
    "Терpимо, сойдёт.",
)

_WELLNESS_BAD = (
    "Плохо.",
    "Мне плохо.",
    "Сегодня плохо себя чувствую.",
    "Неважно.",
    "Совсем не очень.",
    "Очень плохо сегодня.",
    "Чувствую себя паршиво.",
    "Сегодня тяжело.",
    "Состояние плохое.",
    "Мне сегодня хуже обычного.",
    "Плоховато.",
    "Не очень.",
    "Нехорошо.",
    "Плохо себя чувствую.",
    "Мне нехорошо.",
    "Совсем плохо.",
    "Очень плохо.",
    "Плохо сегодня.",
    "Чувствую себя плохо.",
    "Слабенько.",
)

_WELLNESS_BASES: dict[WellnessCategory, tuple[str, ...]] = {
    "good": _WELLNESS_GOOD,
    "normal": _WELLNESS_NORMAL,
    "so_so": _WELLNESS_SO_SO,
    "okay": _WELLNESS_OKAY,
    "bad": _WELLNESS_BAD,
}

# Fast-path / legacy validated mood/sleep/plans phrases.
_MOOD_PHRASES = (
    "Хорошее.",
    "Нормальное.",
    "Плохое.",
    "Не знаю.",
    "Спокойное.",
    "Отличное.",
    "Обычное.",
    "Среднее.",
    "Грустное.",
    "Настроение хорошее.",
)

_SLEEP_PHRASES = (
    "Спал нормально.",
    "Спал хорошо.",
    "Спал плохо.",
    "Мало спал.",
    "Просыпался.",
    "Выспался.",
    "Сон нормальный.",
    "Недоспал.",
    "Спала нормально.",
    "Плохо спал.",
)

_PLANS_PHRASES = (
    "Дома.",
    "Погуляю.",
    "В больницу.",
    "К детям.",
    "В магазин.",
    "По делам.",
    "Никаких планов нет.",
    "Не знаю.",
    "Дома посижу.",
    "К врачу.",
)

_GOODBYE = ("до свидания", "пока", "всего доброго", "до свидания", "пока")
_CONFIRM = ("да", "ага", "конечно", "угу", "да")


def _wellness_pool(category: WellnessCategory) -> list[str]:
    bases = _WELLNESS_BASES[category]
    # 20 bases × 5 suffix variants = 100 phrases
    suffixes = ("", " Да.", " Вроде.", " Сегодня.", " Так.")
    pool: list[str] = []
    for base in bases:
        for suf in suffixes:
            text = (base.rstrip(".") + suf).strip()
            if not text.endswith((".", "!", "?")):
                text += "."
            if text not in pool:
                pool.append(text)
    return pool


def wellness_phrase(category: WellnessCategory, index: int) -> str:
    pool = _wellness_pool(category)
    return pool[index % len(pool)]


def expected_ack_prefix(category: WellnessCategory) -> str:
    if category == "bad":
        return "Жаль это слышать."
    if category in ("so_so", "okay"):
        return "Понятно."
    return "Хорошо."


def slot_answers(
    category: WellnessCategory,
    *,
    family_idx: int,
    variant: int,
) -> SlotAnswers:
    idx = family_idx * 5 + variant
    return SlotAnswers(
        wellness=wellness_phrase(category, idx),
        mood=_MOOD_PHRASES[idx % len(_MOOD_PHRASES)],
        sleep=_SLEEP_PHRASES[(idx + 3) % len(_SLEEP_PHRASES)],
        plans=_PLANS_PHRASES[(idx + 7) % len(_PLANS_PHRASES)],
        goodbye=_GOODBYE[variant % len(_GOODBYE)],
        confirm=_CONFIRM[variant % len(_CONFIRM)],
    )
