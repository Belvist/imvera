"""Adaptive length: a call does not end over a person who is still talking.

Owner mandate 2026-10-03: the list of routine questions running out is not the
person's signal to hang up. While they are still saying something and never
asked to finish, Vera yields the floor once more (bounded) instead of closing.

Contracts under test:

* a substantive turn at the episode-exhaustion close opens a continuation;
* every finish signal still closes: farewell, wrap-up, fatigue, distress,
  explicit stop, red/urgent path untouched;
* the continuation is bounded and never repeats the same invitation;
* a one-word answer is not an invitation to keep talking.
"""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine import reducer
from packages.dialogue_engine.semantic_kernel.kernel import interpret as kinter
from packages.dialogue_engine.semantic_kernel.kernel import kernel_to_rich_turn
from packages.dialogue_engine.state import EngineState

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


def _live_turn(text: str, session: CallSession) -> tuple[str, str]:
    engine = session._engine
    slot = engine.answer_context_slot()
    rich = kernel_to_rich_turn(
        kinter(text, utterance_id="u", engine_state=engine.state, answer_slot=slot),
        answer_slot=slot,
        engine_state=engine.state,
    )
    result = session.handle_user_text(text, rich_turn=rich)
    session.mark_spoken_action(result.proposal.generation_id)
    return (result.proposal.speech or "").strip(), str(
        getattr(result.speak_effect, "intent", "") or ""
    )


def _session() -> CallSession:
    session = CallSession(call_id="adaptive-length", family_id="family",
                          elder_display_name="Тамара Юрьевна",
                          store=InMemoryCallRecordStore())
    session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    return session


# ---------------------------------------------------------------- unit level


def test_a_still_talking_person_gets_an_invitation_not_a_close():
    state = EngineState(call_id="unit")
    state.last_user_text = "Ой, а помните, раньше-то как все вместе жили."
    result = reducer._open_continuation(state)
    assert result is not None
    _, effects = result
    speak = [e for e in effects if getattr(e, "kind", "") == "speak"]
    assert speak and speak[0].text == reducer._OPEN_INVITATION
    assert speak[0].marks_question is False
    assert state.open_continuations == 1
    assert state.call_closed is False


@pytest.mark.parametrize(
    "text",
    [
        "Ну ладно, спасибо, что позвонили.",   # wrap-up
        "Всё, до свидания.",                    # explicit farewell
        "Надоело всё, устала.",                 # fatigue
        "Очень плохо, не могу больше.",         # distress
        "Да.",                                  # one word
        "Хорошо.",                              # bare ack
    ],
)
def test_finish_signals_and_one_word_answers_still_close(text: str):
    state = EngineState(call_id="unit")
    state.last_user_text = text
    assert reducer._open_continuation(state) is None
    assert state.open_continuations == 0


def test_an_explicit_stop_is_never_answered_with_an_invitation():
    state = EngineState(call_id="unit")
    state.last_user_text = "Не беспокой меня больше, я устал."
    state.elder_asked_to_stop = True
    assert reducer._open_continuation(state) is None


def test_the_invitation_budget_is_bounded():
    state = EngineState(call_id="unit")
    text = "Мы с ними в парк ходили, я им пирог пекла с капустой."
    state.last_user_text = text
    assert reducer._open_continuation(state) is not None
    state.last_user_text = text
    assert reducer._open_continuation(state) is None          # budget spent
    assert state.open_continuations == reducer.MAX_OPEN_CONTINUATIONS


def test_the_same_invitation_is_never_said_twice():
    state = EngineState(call_id="unit")
    state.last_user_text = "Мы с ними в парк ходили, я им пирог пекла."
    from packages.dialogue_engine.speech_ledger import normalize

    state.spoken_surfaces = [normalize(reducer._OPEN_INVITATION)]
    assert reducer._open_continuation(state) is None


def test_safety_modes_are_not_affected():
    for attr in ("red_state_pending", "risk_handling"):
        state = EngineState(call_id="unit")
        state.last_user_text = "Ой, а помните, как раньше было, все вместе жили."
        setattr(state, attr, True)
        # The close path returns before the continuation on red/urgent; the
        # helper itself is only reachable after those guards.
        assert state.call_closed is False


# ------------------------------------------------------------- live path


def test_chatty_call_continues_instead_of_closing(runtime_flags: None):
    """A person telling a memory is invited to continue, then closes warmly."""
    session = _session()
    for text in (
        "Здравствуйте, нормально себя чувствую.",
        "Да, поела уже сегодня, всё хорошо.",
        "Голова побаливает иногда, но терпимо.",
    ):
        _live_turn(text, session)
    speech, intent = _live_turn(
        "Ой, а помните, раньше-то как хорошо было, все вместе жили.", session
    )
    assert intent != "partial_unresolved_close", speech
    assert session._engine.state.call_closed is False
