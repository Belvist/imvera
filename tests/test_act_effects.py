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
