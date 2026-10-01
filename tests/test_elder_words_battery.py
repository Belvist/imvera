"""Elder-words battery: unfamiliar old-Russian/dialect complaints must ground.

Every phrase below is how an elderly speaker really reports a symptom.
Bar: an issue mention is grounded (label + site where present) — the
turn must never dissolve into «не расслышала»/silence-drop. If a phrase
fails, the extractor owns the fix, not the test.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine

# phrase -> expected body site ("" = any site or site-less complaint ok,
# but a mention must exist).
BATTERY: list[tuple[str, str]] = [
    ("Неможется мне что-то.", ""),
    ("Расхворалась я.", ""),
    ("Поясницу ломит.", "поясница"),
    ("Суставы ломит.", "суставы"),
    ("Сердце щемит.", "сердце"),
    ("Голова мутная.", "голова"),
    ("В глазах темнеет.", "глаза"),
    ("Живот крутит.", "живот"),
    ("Ногу тянет.", "нога"),
    ("Зуб ноет.", "зуб"),
    ("В боку колет.", "бок"),
    ("Грудь жжёт.", "грудь"),
    ("Виски давит.", "виски"),
    ("Лихорадит меня.", ""),
    ("Кашель душит.", ""),
    ("Мутит меня.", ""),
    ("Ноги отекают.", "ноги"),
    ("Руки немеют.", "руки"),
    ("Руки дрожат.", "руки"),
    ("Шатает меня.", ""),
    ("Ноги подкашиваются.", "ноги"),
    ("Задыхаюсь на лестнице.", ""),
    ("В горле першит.", "горло"),
    ("Голова гудит.", "голова"),
    ("В ушах звенит.", "ухо"),
    ("Ухо заложило.", "ухо"),
    ("Глаза слезятся.", "глаза"),
    ("Спина чешется.", "спина"),
    ("Лицо горит.", "лицо"),
    ("Ночью потею.", ""),
    ("Во рту сохнет.", "рот"),
    ("Горечь во рту.", "рот"),
    ("Изжога замучила.", ""),
    ("Резь внизу живота.", "живот"),
    ("Колено хрустит.", "колено"),
    ("Плечо не поднимается.", "плечо"),
    ("Шею заклинило.", "шея"),
    ("Спина не разгибается.", "спина"),
    ("Пальцы скрючивает.", "пальцы"),
    ("Судорога сводит ногу.", "нога"),
    ("Давление скачет.", "давление"),
    ("Сердце колотится.", "сердце"),
    ("Пульс частит.", ""),
    ("Голова кружится.", "голова"),
    ("Тошнит с утра.", ""),
    ("Рвёт меня.", ""),
    ("Живот слабит.", "живот"),
    ("Закрепило меня.", ""),
    ("Одышка.", ""),
    ("Хрипит в груди.", "грудь"),
    ("Нос заложен.", "нос"),
    ("Горло дерёт.", "горло"),
    ("Кашель сухой.", ""),
    ("Мокрота отходит.", ""),
]


@pytest.mark.parametrize("phrase,site", BATTERY, ids=[b[0] for b in BATTERY])
def test_elder_phrase_grounds(phrase: str, site: str) -> None:
    turn = build_rich_turn_from_text(phrase, utterance_id="u-batt")
    assert turn.issue_mentions, f"no mention grounded for {phrase!r}"
    if site:
        sites = {(m.body_site or "").strip().lower() for m in turn.issue_mentions}
        labels = " ".join((m.label or "").lower() for m in turn.issue_mentions)
        assert site in sites or site in labels, (
            f"site {site!r} not in {sites} / {labels} for {phrase!r}"
        )
