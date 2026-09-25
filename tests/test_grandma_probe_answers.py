"""Grandma's probe answers must be heard, not bounced (demo MP4 gate).

Phrasings from real recordings, asserted at behavior level through the
real CallSession: no repeats, no scolds, no give-ups mid-flow.
"""

from __future__ import annotations

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession

import pytest

pytestmark = pytest.mark.dialogue_engine


def _session(call_id: str) -> CallSession:
    session = CallSession(
        call_id=call_id, family_id="f", elder_display_name="Тамара Андреевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    # Demo config: full check-in (mission requires background goals).
    # Product default stays short-call; flipping it is a separate decision.
    if session._engine is not None:
        session._engine.state.required_background_goals = {"mood", "sleep", "plans"}
    session.mark_spoken_action(opening.proposal.generation_id)
    return session


def _say(session: CallSession, text: str) -> str:
    result = session.handle_user_text(text)
    speech = result.proposal.speech or ""
    # wait_for_continuation Reservations speak on timer expiry, not inline.
    if not speech.strip() and result.proposal.intent == "wait_for_continuation":
        waited = session.handle_wait_expired()
        speech = waited.proposal.speech or ""
        session.mark_spoken_action(waited.proposal.generation_id)
        return speech
    session.mark_spoken_action(result.proposal.generation_id)
    return speech


def test_greeting_gets_kind_reask_not_scold() -> None:
    session = _session("demo-greet")
    result_speech = _say(session, "Привет.")
    assert "двух словах" not in result_speech
    assert "Расскажите, пожалуйста, о самочувствии" not in result_speech
    # Either a kind spoken re-ask or a wait timer that re-speaks the question.
    assert "?" in result_speech or result_speech.strip() == ""


def test_duration_probe_does_not_repeat_on_onset() -> None:
    session = _session("demo-onset")
    _say(session, "Привет.")
    _say(session, "Да не очень, голова болит.")
    speech = _say(session, "Утром как проснулась.")
    engine = session._engine
    assert engine is not None
    assert engine.state.probe_phase != "duration"
    assert engine.state.wellness_duration
    assert "Давно это у вас" not in speech
    assert "Как давно" not in speech


def test_severity_answer_does_not_give_up() -> None:
    session = _session("demo-sev")
    _say(session, "Привет.")
    _say(session, "Да не очень, голова болит.")
    _say(session, "Утром как проснулась.")
    speech = _say(session, "Боль, ну, терпимая.")
    assert "не получилось" not in speech
    assert "До свидания" not in speech


def test_meds_mention_pivots_to_today_question() -> None:
    session = _session("demo-meds")
    _say(session, "Привет.")
    _say(session, "Всё хорошо, только что покушала.")
    _say(session, "Да, было вкусно.")
    speech = _say(session, "Да, от давления.")
    assert "не получилось" not in speech
    assert "принимали" in speech.lower() or "приняли" in speech.lower()


def test_no_midflow_give_up_yellow() -> None:
    session = _session("demo-yellow")
    turns = [
        "Привет.",
        "Да не очень, голова болит.",
        "Утром как проснулась.",
        "Боль, ну, терпимая.",
        "Нет, всё хорошо.",
        "Только голова болит вот.",
    ]
    for text in turns:
        speech = _say(session, text)
        assert "не получилось" not in speech, f"give-up after {text!r}: {speech!r}"
        assert speech.strip() != "", f"silence after {text!r}"


def test_no_midflow_give_up_green() -> None:
    session = _session("demo-green")
    turns = [
        "Привет.",
        "Всё хорошо, только что покушала.",
        "Да, было вкусно.",
        "Да, от давления.",
        "Да, приняла.",
        "Всё хорошо.",
        "Да, выспалась.",
        "Нет, всё хорошо.",
    ]
    for text in turns:
        speech = _say(session, text)
        assert "не получилось" not in speech, f"give-up after {text!r}: {speech!r}"
        assert speech.strip() != "", f"silence after {text!r}"
