"""Closing preserves grounded evidence without answering another question."""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.mission_result import build_call_outcomes, build_mission_result
from packages.dialogue_engine.semantic_kernel.types import Observation
from packages.dialogue_engine.state import GoalLifecycle

pytestmark = pytest.mark.dialogue_engine


def _deliver(engine: DialogueEngine) -> list:
    spoken = []
    while (effect := engine.pop_speak_effect()) is not None:
        spoken.append(effect)
        engine.on_playout_completed(effect.generation, effect.question_id)
    return spoken


def _reply(engine: DialogueEngine, text: str, uid: str) -> list:
    turn = engine.build_rich_turn(text, utterance_id=uid)
    engine.on_user_turn(uid, text, rich_turn=turn)
    return _deliver(engine)


@pytest.mark.parametrize("text", [
    "У меня голова болит. До свидания.",
    "До свидания. Голова сильно болит с утра.",
    "Чувствую себя хорошо, только голова болит. До свидания.",
])
def test_rich_farewell_keeps_grounded_complaint_without_filling_mission(text: str) -> None:
    engine = DialogueEngine(call_id="closing-complaint")
    engine.start()
    _deliver(engine)
    speech = _reply(engine, text, "closing-1")

    assert engine.state.call_closed
    assert engine.state.closing_reason == "goodbye"
    assert speech[-1].intent == "goodbye_final"
    assert "?" not in speech[-1].text
    episode = next(ep for ep in engine.state.issue_episodes.values() if ep.body_site == "голова")
    assert any(m.evidence.quote in text for m in episode.mentions)
    assert "closing-1" in episode.evidence_turn_ids
    if "сильно" in text:
        assert episode.known_attributes["severity"] == "сильно"
        assert "утра" in episode.known_attributes["onset"]
    assert engine.state.goals["wellness"].lifecycle != GoalLifecycle.SATISFIED
    assert engine.state.goals["wellness"].answer is None
    assert build_call_outcomes(engine.state).candidate_family_status != "GREEN"


@pytest.mark.parametrize("text", [
    "Не звоните больше.",
    "Больше не звоните мне.",
    "Не надо звонить.",
    "Не беспокойте меня больше.",
])
def test_addressed_stop_call_keeps_refusal_after_completed_wellness(text: str) -> None:
    engine = DialogueEngine(call_id="closing-refusal")
    engine.start()
    _deliver(engine)
    _reply(engine, "Хорошо.", "wellness-1")
    assert build_mission_result(engine.state).status == "COMPLETED"
    turn = engine.build_rich_turn(text, utterance_id="refusal-1")
    assert turn.control == "stop_call"
    engine.on_user_turn("refusal-1", text, rich_turn=turn)
    speech = _deliver(engine)

    assert speech[-1].intent == "goodbye_final"
    assert "?" not in speech[-1].text
    assert engine.state.closing_reason == "goodbye"
    observation = engine.state.observations["call_refusal"]
    assert observation.evidence == text
    assert observation.source_turn_id == "refusal-1"
    assert "consent_declined" not in engine.state.observations
    outcomes = build_call_outcomes(engine.state)
    assert outcomes.call_outcome == "DECLINED"
    assert outcomes.candidate_family_status == "UNSET"
    assert outcomes.mission_status == "COMPLETED"
    assert f"call_refusal:{text}" in build_mission_result(engine.state).observations


@pytest.mark.parametrize("text", [
    "До свидания.",
    "Не звоните дочке.",
    "Не звоните больше, сказала соседка.",
    "Не звоните — говорила я вчера.",
    'Вчера соседка сказала: «Не звоните больше».',
    "Не звоните означает не пользуйтесь телефоном.",
    "Не болит больше.",
])
def test_near_matches_do_not_become_addressed_call_refusal(text: str) -> None:
    engine = DialogueEngine(call_id="closing-refusal-negative")
    engine.start()
    _deliver(engine)
    _reply(engine, "Хорошо.", "wellness-1")
    _reply(engine, text, "negative-1")
    assert "call_refusal" not in engine.state.observations
    if text == "До свидания.":
        outcomes = build_call_outcomes(engine.state)
        assert outcomes.call_outcome == "COMPLETED"
        assert outcomes.candidate_family_status == "GREEN"


def test_refusal_with_clinical_evidence_does_not_discard_complaint() -> None:
    engine = DialogueEngine(call_id="closing-refusal-clinical")
    engine.start()
    _deliver(engine)
    text = "Не звоните больше. У меня голова болит."
    speech = _reply(engine, text, "refusal-1")
    assert speech[-1].intent == "goodbye_final"
    assert "?" not in speech[-1].text
    episode = next(ep for ep in engine.state.issue_episodes.values() if ep.body_site == "голова")
    assert any(m.evidence.quote in text for m in episode.mentions)
    assert engine.state.observations["call_refusal"].evidence == text
    assert engine.state.goals["wellness"].lifecycle != GoalLifecycle.SATISFIED
    outcomes = build_call_outcomes(engine.state)
    assert outcomes.call_outcome == "DECLINED"
    assert outcomes.candidate_family_status != "GREEN"


def test_addressed_refusal_after_delivered_summary_keeps_closing_evidence() -> None:
    engine = DialogueEngine(call_id="closing-after-summary")
    engine.start()
    _deliver(engine)
    _reply(engine, "Хорошо.", "wellness-1")
    _reply(engine, "Нет, ничего важного.", "its-1")
    assert engine.state.summary_delivered
    speech = _reply(engine, "Не звоните больше.", "refusal-1")
    assert speech[-1].intent == "goodbye_final"
    assert engine.state.observations["call_refusal"].evidence == "Не звоните больше."
    assert build_call_outcomes(engine.state).call_outcome == "DECLINED"
    assert build_call_outcomes(engine.state).candidate_family_status == "UNSET"


def test_safety_still_precedes_farewell_and_refusal() -> None:
    engine = DialogueEngine(call_id="closing-refusal-safety")
    engine.start()
    _deliver(engine)
    speech = _reply(engine, "Не звоните больше. Не могу дышать. До свидания.", "danger-1")
    assert speech[-1].intent == "urgent_close"
    assert build_call_outcomes(engine.state).candidate_family_status != "GREEN"


def test_refusal_quote_and_outcome_survive_real_sdk_persistence() -> None:
    session = CallSession(
        call_id="closing-persisted", family_id="closing-family", store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.mark_spoken_action(opening.proposal.generation_id)
    engine = session._engine
    assert engine is not None
    for number, text in enumerate(("Хорошо.", "Не звоните больше.")):
        turn = engine.build_rich_turn(text, utterance_id=f"u-{number}")
        result = session.handle_user_text(text, rich_turn=turn)
        session.mark_spoken_action(result.proposal.generation_id)
    assert session.finalize_if_needed() == (True, None)
    persisted = session.get_persisted_result()
    assert persisted is not None
    assert persisted.outcomes.call_outcome == "DECLINED"
    assert persisted.outcomes.candidate_family_status == "UNSET"
    assert persisted.public_status is None
    assert not session.state.consent_declined
    assert not session.state.call_revoked
    assert "call_refusal:Не звоните больше." in persisted.mission_result.observations


def test_closing_refusal_quote_survives_full_observation_budget() -> None:
    engine = DialogueEngine(call_id="closing-observation-budget")
    engine.start()
    _deliver(engine)
    for index in range(40):
        engine.state.observations[f"existing-{index}"] = Observation(
            observation_id=f"existing-{index}", attribute="existing", value=f"value-{index}",
        )
    _reply(engine, "Не звоните больше.", "refusal-1")
    notes = build_mission_result(engine.state).observations
    assert len(notes) == 41
    assert notes[-1] == "call_refusal:Не звоните больше."
