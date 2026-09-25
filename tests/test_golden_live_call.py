"""Golden live-call test: trace fs-4d8f5a8b user lines → expected action_ids.

P0d of the Care Dialogue Kernel handoff: truth = live path. Driven
through the RICH path (kernel + rich turns) exactly like CallActor, with
default (short-call) mission config — same as the live call. The old code
answered this call with scold + double goodbye + no severity probe; the
new engine must produce the corrected shape.
"""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.semantic_kernel.kernel import (
    interpret as kernel_interpret,
)
from packages.dialogue_engine.semantic_kernel.kernel import (
    kernel_to_rich_turn,
)

pytestmark = pytest.mark.dialogue_engine

TRACE_LINES = [
    "Привет.",
    "Чувствую себя как-то не очень.",
    "Что-то животик болит у меня.",
    "Не знаю, началось это где-то вчера, наверное. Просто колхози",
    "Не беспокой меня ещё.",
    "Начал зук болит у меня.",
    "Пока.",
]


def _session() -> CallSession:
    session = CallSession(
        call_id="golden-4d8f5a8b", family_id="f",
        elder_display_name="Тамара Юрьевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(opening.proposal.generation_id)
    return session


def _say(session: CallSession, text: str, uid: int):
    engine = session._engine
    assert engine is not None
    engine_state = engine.state
    slot = engine.answer_context_slot()
    kernel_result = kernel_interpret(
        text, utterance_id=f"u{uid}", engine_state=engine_state,
        answer_slot=slot,
    )
    rich_turn = kernel_to_rich_turn(
        kernel_result, answer_slot=slot, engine_state=engine_state,
        mission_provider=None,
    )
    result = session.handle_user_text(text, rich_turn=rich_turn)
    session.mark_spoken_action(result.proposal.generation_id)
    return result.proposal


def test_golden_greeting_is_soft_ack() -> None:
    session = _session()
    p = _say(session, TRACE_LINES[0], 1)
    assert p.intent == "greeting_ack"
    assert "?" not in (p.speech or "")


def test_golden_concern_then_episode_probes() -> None:
    session = _session()
    _say(session, TRACE_LINES[0], 1)
    p1 = _say(session, TRACE_LINES[1], 2)
    assert p1.intent == "probe_concern"
    p2 = _say(session, TRACE_LINES[2], 3)
    assert "onset" in (p2.intent or "")
    p3 = _say(session, TRACE_LINES[3], 4)
    assert "current" in (p3.intent or ""), f"got {p3.intent}: {p3.speech!r}"


def test_golden_no_give_up_midflow() -> None:
    session = _session()
    for i, text in enumerate(TRACE_LINES[:6], 1):
        p = _say(session, text, i)
        assert "не получилось" not in (p.speech or ""), text


def test_golden_single_goodbye_at_close() -> None:
    session = _session()
    speeches: list[str] = []
    for i, text in enumerate(TRACE_LINES, 1):
        p = _say(session, text, i)
        if p.speech and p.speech.strip():
            speeches.append(p.speech)
    farewells = [s for s in speeches if "до свидания" in s.lower()]
    assert len(farewells) == 1, farewells
    assert session._engine is not None
    assert session._engine.state.call_closed is True
