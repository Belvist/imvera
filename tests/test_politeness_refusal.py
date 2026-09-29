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
_LIVE_COMPOSITE_REFUSAL = (
    "Ой, всё, давай пока. Надоело мне, не беспокой меня, я занята."
)
_COMPOSITE_SIBLINGS = [
    "Ой, давай пока, я занята, больше меня не спрашивай.",
    "Всё, пока, не беспокой меня, мне сейчас некогда.",
]


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


@pytest.mark.parametrize(
    "text", [_LIVE_COMPOSITE_REFUSAL, *_COMPOSITE_SIBLINGS]
)
def test_composite_opening_refusal_never_reports_green(text: str) -> None:
    """False-GREEN regression for fs-42bb57a0.

    A composite politeness refusal on the opening wellness turn must be a
    DECLINE, must not fill wellness with the refusal text, and must make a
    follow-up goodbye resolve as a declined call rather than a completed
    green check. A sibling wording already covered by `is_politeness_refusal`
    must pass without a per-quote branch.
    """
    session, out = _run(["Здравствуйте.", text, "Пока."])
    engine = session._engine
    assert engine is not None
    assert normalize_act(_state(), text) == "DECLINE", text
    assert engine.state.last_protocol_act == "DECLINE", text
    assert engine.state.elder_asked_to_stop, text
    assert "?" not in out[1], out[1]
    assert "wellness" not in session._snapshot().facts, session._snapshot().facts
    outcomes = session._snapshot().outcomes
    assert outcomes is not None
    assert outcomes.call_outcome == "DECLINED", outcomes
    assert outcomes.candidate_family_status != "GREEN", outcomes


_REFUSAL = _LIVE_COMPOSITE_REFUSAL


def _outcomes(session):
    snap = session._snapshot()
    assert snap.outcomes is not None
    mission = snap.mission_result.status if snap.mission_result else None
    return snap.outcomes, mission


class TestConsentReengagementInvariant:
    """`mission COMPLETED == re-engagement` is load-bearing: the whole
    consent fix rests on COMPLETED being unreachable without substantive
    user turns. Each sequence below pins one side of it.

    Verified against the state machine (2026-09-29): SATISFIED is written
    only by `_apply_mission_goal_answers` from grounded user-turn answers
    (non-empty utterance-grounded evidence required); machine tails carry
    no goal_answers; legacy mirror is stale (`sync_to_legacy = 0`).
    """

    def test_decline_then_nothing_then_end_is_declined(self) -> None:
        session, _ = _run(["Здравствуйте.", _REFUSAL, "Пока."])
        outcomes, mission = _outcomes(session)
        assert outcomes.call_outcome == "DECLINED", outcomes
        assert mission == "PARTIAL", mission
        assert outcomes.candidate_family_status != "GREEN", outcomes

    def test_decline_then_symptom_keeps_care_first_yellow(self) -> None:
        """Deviation from the naive expectation, documented deliberately:
        in short-call mode only wellness is required, and a volunteered
        symptom SATISFIES it — genuine re-engagement, so mission COMPLETES.
        What must hold: the episode opens (grounding wins) and the
        candidate stays care-first YELLOW, never GREEN, never an
        artificial DECLINED that would hide the symptom.
        """
        session, _ = _run(["Здравствуйте.", _REFUSAL, "Голова болит.", "Пока."])
        engine = session._engine
        assert engine is not None
        sites = {e.body_site for e in engine.state.issue_episodes.values()}
        assert "голова" in sites, sites
        outcomes, mission = _outcomes(session)
        assert mission == "COMPLETED", mission
        assert outcomes.candidate_family_status == "YELLOW", outcomes

    def test_decline_then_full_reengagement_completes(self) -> None:
        session, _ = _run(
            [
                "Здравствуйте.",
                _REFUSAL,
                "Хорошо.",
                "Позавтракал.",
                "Принял таблетки.",
                "Настроение хорошее.",
                "Выспался.",
                "Пока.",
            ]
        )
        outcomes, mission = _outcomes(session)
        assert mission == "COMPLETED", mission
        assert outcomes.call_outcome == "COMPLETED", outcomes
        assert outcomes.candidate_family_status == "GREEN", outcomes

    def test_machine_tails_can_never_complete(self) -> None:
        """THE critical invariant: silences, backchannels and mic-noise
        after a refusal must never flip the mission to COMPLETED. Tails
        carry no goal_answers, so no grounded evidence can accrue."""
        session, _ = _run(
            ["Здравствуйте.", _REFUSAL, "", "Алло.", "Ага.", "Пока."]
        )
        outcomes, mission = _outcomes(session)
        assert mission != "COMPLETED", mission
        assert outcomes.call_outcome == "DECLINED", outcomes
        assert outcomes.candidate_family_status != "GREEN", outcomes

    def test_decline_then_revoke_close_stays_unset(self) -> None:
        session, _ = _run(["Здравствуйте.", _REFUSAL, "Не хочу разговаривать.", "Пока."])
        outcomes, _ = _outcomes(session)
        assert outcomes.call_outcome == "DECLINED", outcomes
        assert outcomes.candidate_family_status == "UNSET", outcomes

    def test_engage_then_revoke_tails_keep_declined(self) -> None:
        """Revoke wins over prior engagement AND over trailing machine
        tails: closing turns after revoke are terminal_noop and must not
        flip anything back to COMPLETED/GREEN."""
        session, _ = _run(
            ["Здравствуйте.", "Хорошо.", "Не хочу разговаривать.", "Пока.", "", "Алло."]
        )
        outcomes, mission = _outcomes(session)
        assert outcomes.call_outcome == "DECLINED", outcomes
        assert outcomes.candidate_family_status == "UNSET", outcomes
        assert mission == "COMPLETED", mission

    def test_consent_withdrawal_recorded_as_separate_fact(self) -> None:
        """ADR-024 outcome data: the refusal moment must be traceable
        independently of the final call_outcome (future ranker learns
        consent=DECLINED -> silence -> call DECLINED from this)."""
        session, _ = _run(["Здравствуйте.", _REFUSAL, "Пока."])
        engine = session._engine
        assert engine is not None
        fact = engine.state.observations.get("consent_declined")
        assert fact, "no consent_declined observation recorded"
        assert "не беспокой" in str(fact).lower(), fact
