"""Live fs-6e3abff0: explicit "nothing hurts" must decline, never urgent.

Two declines ("ничего не беспокоит" + "ничего не болит, всё хорошо")
escalated to urgent_close (false RED to family) because the safety net
read pain markers through negation. Regression test on the RICH path.
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


def _session() -> CallSession:
    session = CallSession(
        call_id="golden-6e3abff0", family_id="f",
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
    slot = engine.answer_context_slot()
    kr = kernel_interpret(
        text, utterance_id=f"u{uid}", engine_state=engine.state, answer_slot=slot
    )
    rt = kernel_to_rich_turn(
        kr, answer_slot=slot, engine_state=engine.state, mission_provider=None
    )
    result = session.handle_user_text(text, rich_turn=rt)
    session.mark_spoken_action(result.proposal.generation_id)
    return result.proposal


def test_double_decline_never_urgent() -> None:
    session = _session()
    _say(session, "Привет. Чувствую себя, ну, более-менее сегодня.", 1)
    _say(session, "И ничего вроде не беспокоит.", 2)
    p = _say(session, "Ничего не болит, всё хорошо.", 3)
    assert p.intent != "urgent_close", f"false RED: {p.speech!r}"
    assert "передам" not in (p.speech or "").lower()


def test_negated_pain_is_not_complaint() -> None:
    from packages.dialogue_engine.check_path import (
        complaint_without_negation,
    )

    assert complaint_without_negation("Ничего не болит, всё хорошо.") is False
    assert complaint_without_negation("И ничего вроде не беспокоит.") is False
    assert complaint_without_negation("Голова болит.") is True
    assert complaint_without_negation("Что-то животик болит у меня.") is True
    assert complaint_without_negation("Не очень, голова болит.") is True
