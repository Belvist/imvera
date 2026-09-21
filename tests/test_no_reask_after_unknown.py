"""Re-ask invariant: a not-recalled answer resolves, never retries.

"Когда началось?" -> "Не помню" must close the onset question as UNKNOWN
with evidence and advance. The same semantic question must not be asked
again without new evidence or explicit user repeat.
"""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
from packages.dialogue_engine.state import Question, QuestionPhase

pytestmark = pytest.mark.dialogue_engine


def _engine() -> DialogueEngine:
    engine = DialogueEngine(call_id="reask", elder_display_name="Тест")
    engine.start()
    return engine


def _deliver_onset(engine: DialogueEngine):
    from packages.dialogue_engine.state import EngineState

    state: EngineState = engine.state
    state.delivered_question = Question(
        question_id="q-onset-1",
        slot="onset",
        text="Когда это началось?",
        phase=QuestionPhase.DELIVERED,
        intent="ask_onset",
        goal_id="onset",
    )
    return state


def _speak_intents(effects: list) -> list[str]:
    return [e.intent for e in effects if isinstance(e, SpeakEffect)]


def test_not_recalled_closes_question() -> None:
    engine = _engine()
    state = _deliver_onset(engine)
    sem = SemanticTurn(
        act=SemanticAct.ANSWER,
        target_slot="onset",
        confidence=0.9,
        source_quote="Не помню.",
        value="Не помню.",
        not_recalled=True,
    )
    effects = engine.on_user_turn("t1", "Не помню.", sem)
    assert state.slots["onset"] == SlotStatus.UNRESOLVED
    assert state.observations.get("onset_unknown") == "Не помню."
    assert state.delivered_question is None
    intents = _speak_intents(effects)
    assert not any("onset" in intent for intent in intents), intents


def test_deterministic_phrase_variants() -> None:
    for text in ("не помню уже", "Не могу вспомнить.", "Затрудняюсь сказать"):
        engine = _engine()
        state = _deliver_onset(engine)
        sem = SemanticTurn(
            act=SemanticAct.ANSWER,
            target_slot="onset",
            confidence=0.5,
            source_quote=text,
            value=text,
        )
        engine.on_user_turn("t1", text, sem)
        assert state.slots["onset"] == SlotStatus.UNRESOLVED, text
        assert state.delivered_question is None, text


def test_plain_uncertain_still_routes_normally() -> None:
    """'Не знаю' alone is ambiguous — must NOT trigger unknown-resolve."""
    engine = _engine()
    state = _deliver_onset(engine)
    sem = SemanticTurn(
        act=SemanticAct.ANSWER,
        target_slot="onset",
        confidence=0.5,
        source_quote="Не знаю.",
        value="Не знаю.",
    )
    engine.on_user_turn("t1", "Не знаю.", sem)
    assert state.slots.get("onset") != SlotStatus.UNRESOLVED
    assert "onset_unknown" not in state.observations


def test_normal_answer_still_fills() -> None:
    engine = _engine()
    state = _deliver_onset(engine)
    sem = SemanticTurn(
        act=SemanticAct.ANSWER,
        target_slot="onset",
        confidence=0.9,
        source_quote="Вчера.",
        value="Вчера.",
    )
    engine.on_user_turn("t1", "Вчера.", sem)
    assert "onset_unknown" not in state.observations
