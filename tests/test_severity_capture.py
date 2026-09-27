"""A severity answer must be recorded even when another step is pending.

«Живот болит.» → Vera asks the current probe → «Сильно.» is a real answer
about how much it hurts, and it was being discarded (hard-battery `abdominal`,
live fs-4d8f5a8b). Two things are pinned:

- the severity evidence is kept;
- nothing is fabricated: a `current` answer must never be written into
  `onset`/`duration` by this path (a generalized version did exactly that,
  and «Сейчас не беспокоит.» is not a temporal anchor).
"""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.semantic_kernel.kernel import (
    interpret,
    kernel_to_rich_turn,
)

pytestmark = pytest.mark.dialogue_engine


def _session() -> tuple[CallSession, object]:
    session = CallSession(
        call_id="sev-capture",
        family_id="f",
        elder_display_name="Тамара Юрьевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(opening.proposal.generation_id)
    return session, session._engine


def _say(session: CallSession, engine, text: str, i: int) -> str:
    slot = engine.answer_context_slot()
    rich = kernel_to_rich_turn(
        interpret(text, utterance_id=f"u{i}", engine_state=engine.state, answer_slot=slot),
        answer_slot=slot,
        engine_state=engine.state,
    )
    result = session.handle_user_text(text, rich_turn=rich)
    session.mark_spoken_action(result.proposal.generation_id)
    return (result.proposal.speech or "").strip()


def _episode(engine):
    eps = [e for e in engine.state.issue_episodes.values() if e.body_site == "живот"]
    assert eps, "no abdominal episode"
    return eps[0]


def test_out_of_order_severity_is_kept() -> None:
    session, engine = _session()
    _say(session, engine, "Привет.", 0)
    _say(session, engine, "Живот болит.", 1)
    _say(session, engine, "Сильно.", 2)
    assert _episode(engine).known_attributes.get("severity"), dict(
        _episode(engine).known_attributes
    )


def test_no_fabrication_into_temporal_steps() -> None:
    """«Сейчас не беспокоит.» answers `current`, not when it started."""
    session, engine = _session()
    _say(session, engine, "Привет.", 0)
    _say(session, engine, "Живот болит.", 1)
    _say(session, engine, "Сильно.", 2)
    _say(session, engine, "Сейчас не беспокоит.", 3)
    attrs = dict(_episode(engine).known_attributes)
    assert attrs.get("severity")
    # duration must never be a copy of a `current` sentence
    assert attrs.get("duration") != "Сейчас не беспокоит.", attrs


def test_severity_is_not_overwritten() -> None:
    session, engine = _session()
    _say(session, engine, "Привет.", 0)
    _say(session, engine, "Живот болит.", 1)
    _say(session, engine, "Сильно.", 2)
    first = _episode(engine).known_attributes.get("severity")
    _say(session, engine, "Терпимо.", 3)
    assert _episode(engine).known_attributes.get("severity") == first
