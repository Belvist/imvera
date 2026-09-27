"""CDK Step 2: acts drive NeedQueue/Action (not lexical branches).

- DECLINE → pain_site_probe/concern_probe forbidden; later vague turns
  still must not re-probe (fs-6e3abff0 class).
- ISSUE_SITE → severity queued and served before ITS.
"""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession

pytestmark = pytest.mark.dialogue_engine


def _session(call_id: str) -> CallSession:
    session = CallSession(
        call_id=call_id, family_id="f", elder_display_name="Тамара Юрьевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(opening.proposal.generation_id)
    return session


def _say(session: CallSession, text: str) -> str:
    result = session.handle_user_text(text)
    speech = result.proposal.speech or ""
    session.mark_spoken_action(result.proposal.generation_id)
    return speech


def _engine(session: CallSession):
    engine = session._engine
    assert engine is not None
    return engine


def test_decline_forbids_concern_reprobe() -> None:
    session = _session("act-decline")
    _say(session, "Привет. Чувствую себя более-менее.")
    _say(session, "И ничего вроде не беспокоит.")
    engine = _engine(session)
    assert "concern_probe" in engine.state.forbidden_actions
    assert "pain_site_probe" in engine.state.forbidden_actions
    # A later vague turn must NOT resurrect the concern probe.
    speech = _say(session, "Поел.")
    assert "голов" not in speech.lower() and "сердце" not in speech.lower()
    assert "живот" not in speech.lower()


def test_issue_site_enqueues_severity_before_its() -> None:
    session = _session("act-site")
    _say(session, "Привет.")
    _say(session, "Голова болит.")
    engine = _engine(session)
    assert "severity" in engine.state.queued_needs
    speech = _say(session, "Утром началось.")
    assert "сильн" in speech.lower() or "терпим" in speech.lower()
    # Queue consumed by the probe: ITS later must not re-ask severity.
    assert "severity" not in _engine(session).state.queued_needs


def _fresh_state():
    from packages.dialogue_engine.engine import DialogueEngine

    engine = DialogueEngine(call_id="act-table", elder_display_name="Тест")
    engine.start()
    return engine.state


def test_act_table_no_preopened_probe_required() -> None:
    """DoD#5: state×text→act without a pre-opened concern probe."""
    from packages.dialogue_engine.protocol.acts import normalize_act

    cases = [
        # (setup, text, expected_act)
        ("wellness_open", "И ничего вроде не беспокоит.", "DECLINE"),
        ("wellness_open", "Ничего не болит, всё хорошо.", "DECLINE"),
        ("wellness_open", "Да нет, ничего не болит.", "DECLINE"),  # new wording
        ("wellness_open", "Поел.", None),
        ("wellness_open", "Не скажу.", None),
        ("wellness_open", "Отстань.", None),  # hostile: escalation, not politeness
        # Politeness refusal = «stop asking», a closed act (DECLINE). Distinct
        # from denial of the complaint; hostile wording above must NOT map here.
        ("wellness_open", "Не беспокой меня ещё.", "DECLINE"),
        ("wellness_open", "не хочу об этом говорить", "DECLINE"),
        ("wellness_open", "Больше не спрашивай.", "DECLINE"),
        ("wellness_open", "Оставьте меня, пожалуйста.", "DECLINE"),
        ("wellness_open", "Хватит меня спрашивать.", None),  # hostile register
        ("wellness_open", "Голова болит.", "ISSUE_SITE"),
        ("wellness_open", "Хорошо.", None),  # bare positive: not DECLINE
    ]
    for setup, text, expected in cases:
        state = _fresh_state()
        assert setup == "wellness_open"  # single setup in this table
        assert normalize_act(state, text) == expected, (text, expected)


def test_act_lattice_table() -> None:
    """DoD: state×text→act table, new wordings need no new code."""
    from packages.dialogue_engine.protocol.acts import normalize_act

    cases = [
        ("И ничего вроде не беспокоит.", "DECLINE"),
        ("Да нет, ничего не болит.", "DECLINE"),  # fresh wording, same act
        ("Более-менее.", "WELLNESS_SO_SO"),
        ("Да так пойдёт.", "WELLNESS_SO_SO"),
        ("Средне.", "WELLNESS_SO_SO"),
        ("Терпимо.", "WELLNESS_SO_SO"),
        ("Голова болит.", "ISSUE_SITE"),
        ("Живот прихватило.", "ISSUE_SITE"),
        ("Хорошо.", "WELLNESS_OK"),  # needs wellness asked; set below
        ("Нормально.", "WELLNESS_OK"),  # mild positive, not decline
        ("Поел.", None),
        ("Отстань.", None),
    ]
    for text, expected in cases:
        st = _fresh_state()
        if expected in ("WELLNESS_OK",):
            from packages.dialogue_engine.state import Question, QuestionPhase

            st.delivered_question = Question(
                question_id="g", slot="wellness", text="Как вы?",
                phase=QuestionPhase.DELIVERED, intent="check_wellness",
            )
        assert normalize_act(st, text) == expected, (text, expected)
