"""Partial close must not lie about what was learned.

Live fs-0f94e538: three positive answers followed by «Сейчас не получилось
узнать, как у вас дела» — factually wrong and inhumane to hear. When facts
are on record the close thanks and confirms; the give-up wording survives
only for truly empty calls.
"""

from __future__ import annotations

import time

import pytest

from packages.contracts.enums import SlotStatus
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.reducer import _close_partial

pytestmark = pytest.mark.dialogue_engine


def _close_text_with_slots(filled: dict[str, str]) -> str:
    session = CallSession(
        call_id=f"pc-{time.time_ns()}",
        family_id="partial-close",
        elder_display_name="Тамара Юрьевна",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    eng = session._engine
    assert eng is not None
    for slot, value in filled.items():
        eng.state.slots[slot] = SlotStatus.FILLED
        eng.state.slot_values[slot] = value
    _, effects = _close_partial(eng.state)
    texts = [e.text for e in effects if isinstance(e, SpeakEffect)]
    assert texts, "partial close emitted nothing"
    return texts[0]


def test_close_with_facts_thanks_instead_of_giving_up() -> None:
    text = _close_text_with_slots(
        {"wellness": "Хорошо себя чувствую.", "mood": "Настроение хорошее."}
    )
    assert "не получилось" not in text.lower(), text
    assert text.startswith("Спасибо, всё записала."), text


def test_close_without_facts_keeps_give_up_wording() -> None:
    text = _close_text_with_slots({})
    assert "не получилось узнать" in text.lower(), text
