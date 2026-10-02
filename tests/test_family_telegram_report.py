"""Telegram family report renders truthfully (no DB needed)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools.family_notify.telegram_report import build_message

pytestmark = pytest.mark.dialogue_engine


def _snap(**kw):
    base = {
        "outcomes": {},
        "metadata": {},
        "facts": {},
        "observations": [],
        "call_ended": True,
    }
    base.update(kw)
    return SimpleNamespace(model_dump=lambda mode="json": base)


def test_technical_call_says_partial() -> None:
    msg = build_message(
        "fs-x",
        _snap(outcomes={"candidate_family_status": "UNSET", "call_outcome": "TECHNICAL"}),
    )
    assert "технической" in msg
    assert "Нет данных" in msg


def test_yellow_shows_concern_and_facts() -> None:
    msg = build_message(
        "fs-x",
        _snap(
            outcomes={"candidate_family_status": "YELLOW"},
            metadata={"elder_display_name": "Тест", "wellness_concern": "болит голова"},
            facts={"mood": "нормальное"},
            call_ended=True,
        ),
    )
    assert "Нужно внимание" in msg
    assert "болит голова" in msg
    assert "Настроение: нормальное" in msg
