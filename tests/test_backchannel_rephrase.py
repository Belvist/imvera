"""Backchannel ("ага") at a pending question → ack + rephrased re-ask.

Owner decision: never scold ("расскажите в двух словах"), never stall in
silence; rephrase works at ANY pending question, not just wellness.
"""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession

pytestmark = pytest.mark.dialogue_engine


def _session(call_id: str, full: bool = False) -> CallSession:
    session = CallSession(
        call_id=call_id, family_id="f", elder_display_name="Тамара Юрьевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    if full and session._engine is not None:
        session._engine.state.required_background_goals = {"mood", "sleep", "plans"}
    session.mark_spoken_action(opening.proposal.generation_id)
    return session


def _say(session: CallSession, text: str) -> str:
    result = session.handle_user_text(text)
    speech = result.proposal.speech or ""
    session.mark_spoken_action(result.proposal.generation_id)
    return speech


def _to_mood_q(session: CallSession) -> str:
    _say(session, "Привет.")
    _say(session, "Всё хорошо, только что покушала.")
    _say(session, "Да, было вкусно.")
    _say(session, "Да, от давления.")
    mood_q = _say(session, "Да, приняла.")
    # Contract migrated: any member of the mood pool counts as the mood
    # question (per-call rotation may open on a variant without the word
    # «настроение», e.g. «Не тревожит ничего сегодня?»).
    from packages.dialogue_engine import questions as _Q
    assert mood_q.strip() in _Q._SLOT_QUESTION_VARIANTS["mood"], (
        f"expected mood Q, got: {mood_q!r}"
    )
    return mood_q


def test_aga_at_wellness_rephrases_not_scolds() -> None:
    session = _session("bc-well")
    opening_q = session._engine.state.delivered_question.text
    speech = _say(session, "Ага.")
    assert "двух словах" not in speech
    assert "?" in speech
    assert speech.strip() != opening_q.strip()


def test_aga_at_mood_rephrases() -> None:
    session = _session("bc-mood", full=True)
    mood_q = _to_mood_q(session)
    from packages.dialogue_engine import questions as _Q
    assert mood_q.strip() in _Q._SLOT_QUESTION_VARIANTS["mood"]
    speech = _say(session, "Ага.")
    assert "двух словах" not in speech
    assert "?" in speech
    assert speech.strip() != mood_q.strip()


def test_aga_at_duration_probe_rephrases() -> None:
    session = _session("bc-dur")
    _say(session, "Привет.")
    dur_q = _say(session, "Да не очень, голова болит.")
    speech = _say(session, "Ага.")
    assert "?" in speech
    assert speech.strip() != dur_q.strip()


def test_triple_aga_closes_honestly_without_hang() -> None:
    session = _session("bc-triple")
    speeches = [_say(session, "Ага.") for _ in range(3)]
    assert all(isinstance(s, str) for s in speeches)
    engine = session._engine
    assert engine is not None
    assert engine.state.call_closed is True


@pytest.mark.parametrize(
    "phrase",
    ["Да, слушаю.", "Слушаю вас.", "Да, говорите.", "Я здесь.", "На связи."],
)
def test_presence_signal_is_not_answered_with_i_did_not_hear(phrase: str) -> None:
    """The person is on the line and ready — that is not an unclear answer."""
    session = _session(f"presence-{abs(hash(phrase)) % 10000}")
    opening_q = session._engine.state.delivered_question.text
    speech = _say(session, phrase)
    assert "не расслышала" not in speech.lower(), speech
    assert "не разобрать" not in speech.lower(), speech
    assert "?" in speech, speech
    assert speech.strip() != opening_q.strip(), speech


def test_presence_signal_at_a_yes_no_question_still_answers_nothing() -> None:
    """A presence signal never becomes a yes: the question must be re-asked."""
    session = _session("presence-yn", full=True)
    _say(session, "Привет.")
    _say(session, "Всё хорошо, только что покушала.")
    _say(session, "Да, было вкусно.")
    meds_q = _say(session, "Да, от давления.")
    assert "?" in meds_q
    speech = _say(session, "Да, слушаю.")
    assert "не расслышала" not in speech.lower(), speech
    assert session._engine.state.slot_values.get("medication", "") == ""
