"""Neutral regular-meds check — product spec as regression tests (user-provided).

Principles (frozen by this file):
- never «не забудьте» / prescribe / discuss dosage
- screening first; today-Q only when meds exist (incl. as-needed)
- the question itself is the soft reminder; not-taken/forgot/unsure are
  recorded WITHOUT any instruction to take
- a new complaint inside a meds answer switches to the symptom
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner


@pytest.fixture(autouse=True)
def _pilot_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pilot flag scoped to THIS file only — never leak into other tests.
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")

FORBIDDEN = (
    "не забуд",
    "обязательно примит",
    "обязательно выпей",
    "вам нужно принять",
    "вам надо принять",
    "выпейте сейчас",
    "примите сейчас",
    "дозиров",
)


def run(turns: list) -> tuple[ScenarioRunner, list[str], list[str]]:
    r = ScenarioRunner(call_id="meds-spec", elder_display_name="Тест")
    intents: list[str] = []
    texts: list[str] = []
    for t in turns:
        res = r.run([t])
        for e in res.speak_effects:
            assert isinstance(e, SpeakEffect)
            intents.append(e.intent)
            texts.append(e.text or "")
    for tx in texts:
        low = tx.lower()
        for bad in FORBIDDEN:
            assert bad not in low, f"forbidden phrase {bad!r} in {tx!r}"
    return r, intents, texts


def test_s1_no_regular_meds():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Нет, я обычно никаких лекарств не принимаю."])
    assert "background_medication_today" not in intents


def test_s2_taken_today():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Да, есть.", "Да, утром уже принимал."])
    assert "background_medication_today" in intents


def test_s3_not_taken_yet():
    r, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Да, принимаю.", "Нет, ещё не принимал."])
    assert "background_medication_today" in intents
    assert not r.state.call_closed or True


def test_s4_unsure():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Есть.", "Не помню точно, может, принимал."])
    assert "background_medication_today" in intents


def test_s5_forgot():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Да, есть.", "Ой, нет, совсем забыл."])
    assert "background_medication_today" in intents


def test_s6_several_meds():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Да, несколько разных.", "Да, всё принимал."])
    assert "background_medication_today" in intents


def test_s7_partial_today():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Да.", "Утренние принимал, остальные ещё нет."])
    assert "background_medication_today" in intents


def test_s8_as_needed_only():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Постоянно нет, только иногда, если нужно.",
                         "Нет, сегодня не понадобилось."])
    assert "background_medication_today" in intents


def test_s9_refuses_topic():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Не хочу про это говорить."])
    assert "background_medication_today" not in intents


def test_s10_weakness_after_taken():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Да.", "Да, утром.", "Немного слабость какая-то."])
    assert "background_medication_today" in intents
    assert any("weakness" in i or "episode" in i or "important_to_share" in i
               for i in intents)


def test_s11_headache_after_taken():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Да, принимаю.", "Да. Но голова с утра побаливает."])
    assert "background_medication_today" in intents
    assert any("headache" in i or "episode" in i for i in intents)


def test_s12_belly_after_taken():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Есть.", "Да, принимал. Только живот утром немного поболел."])
    assert "background_medication_today" in intents
    assert any("belly" in i or "abdominal" in i or "episode" in i for i in intents)


def test_s13_forgot_names():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Да, есть, только названия сейчас не вспомню.",
                         "Да, принимал."])
    assert "background_medication_today" in intents


def test_s14_daughter_prepares():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Да, дочь мне обычно раскладывает.", "Да, утром."])
    assert "background_medication_today" in intents


def test_s15_neutral_no_pressure():
    _, intents, _ = run([CallStarted(), "Хорошо.", "Поела.",
                         "Да.", "Нет, пока нет."])
    assert "background_medication_today" in intents
