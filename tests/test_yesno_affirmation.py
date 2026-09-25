"""Affirmation ("ага"/"да") to a yes/no question IS an answer.

Owner: "принимали таблетки?" + "ага" = valid yes. Only open questions
("как самочувствие?") treat "ага" as backchannel with rephrase.
"""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession

pytestmark = pytest.mark.dialogue_engine


def _session(call_id: str) -> CallSession:
    session = CallSession(
        call_id=call_id, family_id="f", elder_display_name="Тамара Андреевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    if session._engine is not None:
        session._engine.state.required_background_goals = {"mood", "sleep", "plans"}
    session.mark_spoken_action(opening.proposal.generation_id)
    return session


def _say(session: CallSession, text: str) -> str:
    result = session.handle_user_text(text)
    speech = result.proposal.speech or ""
    session.mark_spoken_action(result.proposal.generation_id)
    return speech


def _to_meds_today(session: CallSession) -> str:
    _say(session, "Привет.")
    _say(session, "Всё хорошо, только что покушала.")
    _say(session, "Да, было вкусно.")
    q = _say(session, "Да, от давления.")
    assert "приняли" in q.lower(), f"expected meds-today Q, got: {q!r}"
    return q


def test_aga_to_meds_today_means_took() -> None:
    session = _session("yn-meds")
    _to_meds_today(session)
    speech = _say(session, "Ага.")
    engine = session._engine
    assert engine is not None
    assert engine.state.observations.get("coverage_medication_today") == "Ага."
    assert "не получилось" not in speech


def test_da_to_meds_today_means_took() -> None:
    session = _session("yn-meds-da")
    _to_meds_today(session)
    speech = _say(session, "Да.")
    engine = session._engine
    assert engine is not None
    assert engine.state.observations.get("coverage_medication_today") == "Да."
    assert "не получилось" not in speech


def test_net_to_meds_today_recorded_not_nagged() -> None:
    session = _session("yn-meds-net")
    _to_meds_today(session)
    speech = _say(session, "Нет.")
    engine = session._engine
    assert engine is not None
    assert engine.state.observations.get("coverage_medication_today") == "Нет."
    assert "приняли" not in speech.lower() or "?" not in speech
    assert "не получилось" not in speech


def test_aga_to_open_question_stays_rephrase() -> None:
    session = _session("yn-open")
    opening_q = session._engine.state.delivered_question.text
    speech = _say(session, "Ага.")
    assert "?" in speech
    assert speech.strip() != opening_q.strip()
