"""«Не беспокой меня» must stop the questions, not the caring.

Live fs-4d8f5a8b: the elder said «Не беспокой меня ещё.» and Vera answered
with the next question («Есть ли ещё что-то важное…»). For an elder that is
the worst possible answer.

Two boundaries are pinned here:

- a POLITE refusal routes to the existing closed act DECLINE and yields a
  warm acknowledgement with no question;
- a HOSTILE refusal («Отстань.», «Хватит меня спрашивать») keeps the
  pre-existing escalation path (urgent_close, concern_status unspecified) —
  politeness must not disarm safety;
- a symptom reported AFTER a refusal is still recorded and probed — safety
  and grounding outrank politeness.
"""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.check_path import (
    complaint_without_negation,
    is_politeness_refusal,
)
from packages.dialogue_engine.protocol.acts import normalize_act
from packages.dialogue_engine.semantic_kernel.kernel import (
    interpret,
    kernel_to_rich_turn,
)
from packages.dialogue_engine.state import EngineState

pytestmark = pytest.mark.dialogue_engine

_POLITE = [
    "Не беспокой меня ещё.",
    "не хочу об этом говорить",
    "Больше не спрашивай.",
    "Оставьте меня, пожалуйста.",
    "Не надо мне вопросов.",
]
_HOSTILE = ["Отстань.", "Хватит меня спрашивать."]


def _state() -> EngineState:
    return EngineState(call_id="t", elder_display_name="T")


def _run(lines: list[str], call_id: str = "refusal"):
    session = CallSession(
        call_id=call_id,
        family_id="f",
        elder_display_name="Тамара Юрьевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(opening.proposal.generation_id)
    out = []
    engine = session._engine
    assert engine is not None
    for i, text in enumerate(lines):
        slot = engine.answer_context_slot()
        rich = kernel_to_rich_turn(
            interpret(text, utterance_id=f"u{i}", engine_state=engine.state, answer_slot=slot),
            answer_slot=slot,
            engine_state=engine.state,
        )
        result = session.handle_user_text(text, rich_turn=rich)
        session.mark_spoken_action(result.proposal.generation_id)
        out.append((result.proposal.speech or "").strip())
    return session, out


@pytest.mark.parametrize("text", _POLITE)
def test_polite_refusal_is_an_act_not_silence(text: str) -> None:
    assert is_politeness_refusal(text), text
    assert normalize_act(_state(), text) == "DECLINE", text


@pytest.mark.parametrize("text", _HOSTILE)
def test_hostile_refusal_does_not_get_the_polite_path(text: str) -> None:
    """Politeness must not disarm the deliberate hostile escalation."""
    assert not is_politeness_refusal(text), text


@pytest.mark.parametrize("text", _POLITE)
def test_refusal_is_never_read_as_a_complaint(text: str) -> None:
    assert not complaint_without_negation(text), text


def test_bigger_word_is_not_pain() -> None:
    """«Больше» starts with «бол» and used to read as a pain complaint.

    Saying «не беспокой меня больше» must never arm a complaint.
    """
    assert not complaint_without_negation("Больше не беспокой меня.")
    assert not complaint_without_negation("Больше не спрашивай.")
    assert complaint_without_negation("Голова болит сильно.")
    assert complaint_without_negation("Меня тошнит.")


def test_refusal_gets_a_warm_ack_and_no_question() -> None:
    _, out = _run(
        [
            "Здравствуйте.",
            "Чувствую себя как-то не очень.",
            "Что-то животик болит у меня.",
            "Не беспокой меня ещё.",
        ]
    )
    answer = out[-1]
    assert "?" not in answer, answer
    assert answer.strip(), "refusal must not be met with silence"


def test_symptom_after_refusal_is_still_recorded() -> None:
    """Safety outranks politeness: a new complaint is still grounded."""
    session, out = _run(
        [
            "Здравствуйте.",
            "Что-то животик болит у меня.",
            "Не беспокой меня ещё.",
            "Начал зук болит у меня.",
        ]
    )
    engine = session._engine
    assert engine is not None
    sites = {e.body_site for e in engine.state.issue_episodes.values() if e.body_site}
    assert "зук" in sites, sites
    assert "?" in out[-1], out[-1]
