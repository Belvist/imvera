"""Wellness answer/skip/garbage boundary (anti-patch loop).

The deterministic tier-1 (polarity/complaint/fact anchors) must stay the
owner of polarity. The classifier is tier-2: it only decides whether an
anchor-miss is still a substantive wellness answer (record own words),
a skip (refuse the dimension), or garbage (re-ask, never close the slot).

Critical: on the pre-wellness model the judge answered `answer` to
everything incl. garbage with p>=0.96 (slot token washed out). These tests
pin the boundary AFTER training with wellness rows.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.slotclf import judge

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture(autouse=True)
def _pilot_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    # slotclf is pilot-only by contract (returns None with the flag off),
    # same as test_critical_ladder.
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")

_WELLNESS_ANSWERS = [
    "хорошо",
    "нормально",
    "плохо",
    "мне плохо",
    "более-менее",
    "по состоянию мне более-менее",
    "мне так себе",
    "средне",
    "средненько",
    "терпимо",
    "ни шатко ни валко",
    "кое-как",
    "помаленьку",
    "неважно себя чувствую",
]

_WELLNESS_GARBAGE = [
    "абракадабра",
    "белиберда",
    "трамвай",
    "тарабарщина",
    "ага",
    "угу",
    "алло",
    "э-э",
    "у мужа плохо",  # other-person alone: no speaker fact
    "не знаю",  # not a valid wellness answer: re-ask, never skip to food
]

_WELLNESS_SKIP = [
    "не скажу",
    "дальше",
    "пропусти",
]


@pytest.mark.parametrize("text", _WELLNESS_ANSWERS)
def test_wellness_substantive_is_answer(text: str) -> None:
    assert judge("wellness", text) == "answer"


@pytest.mark.parametrize("text", _WELLNESS_GARBAGE)
def test_wellness_debris_is_garbage(text: str) -> None:
    assert judge("wellness", text) == "garbage"


@pytest.mark.parametrize("text", _WELLNESS_SKIP)
def test_wellness_refusal_is_skip(text: str) -> None:
    assert judge("wellness", text) == "skip"
