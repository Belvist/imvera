"""Volunteered-topic ack + distress empathy, live-faithful path.

NOTE: ScenarioRunner builds rich turns via build_rich_turn_from_text and
does NOT mark the greeting spoken — it diverges from the live CallActor
path (proven on fs-9a5cfc31: runner says nutrition, live said concern).
These tests drive CallSession.handle_user_text with kernel-built rich
turns and a delivered greeting, exactly like CallActor does.
"""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import interpret_user_turn
from packages.dialogue.session import CallSession
from packages.dialogue_engine.semantic_kernel.kernel import (
    interpret as kinter,
)
from packages.dialogue_engine.semantic_kernel.kernel import (
    kernel_to_rich_turn,
)

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture
def runtime_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "IMVERA_DIALOGUE_ENGINE": "1",
        "IMVERA_COVERAGE_LADDER": "1",
        "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
        "IMVERA_ACTION_POLICY_MODE": "off",
    }.items():
        monkeypatch.setenv(name, value)


def _live_turn(text: str, answer_slot: str = "wellness") -> tuple[str, str]:
    session = CallSession(
        call_id="faithful", family_id="f", store=InMemoryCallRecordStore()
    )
    start = session.start()
    session.mark_spoken_action(
        start.proposal.generation_id if hasattr(start.proposal, "generation_id") else ""
    )
    engine = session._engine
    interp = interpret_user_turn(session.state, text)
    parsed = kinter(
        text, utterance_id="u-1", engine_state=engine.state, answer_slot=answer_slot
    )
    rich = kernel_to_rich_turn(
        parsed, answer_slot=answer_slot, engine_state=engine.state
    )
    result = session.handle_user_text(
        text, interp=interp, utterance_id="u-1", rich_turn=rich
    )
    return result.proposal.speech, result.proposal.intent


@pytest.mark.usefixtures("runtime_flags")
def test_volunteered_food_acknowledged_before_moving_on() -> None:
    speech, intent = _live_turn("Привет. Всё хорошо. Только что покушала.")
    assert "беспокоит" not in speech.lower(), speech
    assert speech.startswith("Хорошо, что поели."), speech


@pytest.mark.usefixtures("runtime_flags")
def test_distress_gets_empathy_before_concern_probe() -> None:
    speech, intent = _live_turn("Ой, привет, очень плохо.")
    assert intent == "probe_concern", (intent, speech)
    assert speech.startswith("Сочувствую."), speech


@pytest.mark.usefixtures("runtime_flags")
def test_no_distress_no_prefix() -> None:
    speech, intent = _live_turn("Что-то голова побаливает.")
    if intent == "probe_concern":
        assert not speech.startswith("Сочувствую."), speech
