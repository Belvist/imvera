"""Slice 1: arbitrary CallMission via CallSession → DialogueEngine → understand → apply."""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.mission import (
    CallMission,
    CustomMissionRequiresDialogueEngine,
    GoalDefinition,
)
from packages.dialogue_engine.state import GoalLifecycle, Question, QuestionPhase
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

_UTTERANCE = (
    "Да, утром оплатил. Только отопление опять еле работает, "
    "и дочь вечером обещала зайти."
)


def _custom_mission() -> CallMission:
    return CallMission(
        mission_id="app-home-check-1",
        goals=(
            GoalDefinition(
                goal_id="utilities_paid",
                description="Узнать, оплачены ли коммунальные счета",
                prompt_hint="Успели сегодня оплатить коммунальные счета?",
                required=True,
                priority=10,
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
            ),
            GoalDefinition(
                goal_id="groceries_help",
                description="Узнать, нужна ли помощь с продуктами",
                prompt_hint="Нужна ли сегодня помощь с продуктами?",
                required=True,
                priority=20,
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
            ),
        ),
        preset=None,
    )


def _session_with_mission(monkeypatch: pytest.MonkeyPatch) -> CallSession:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    session = CallSession(
        call_id="mission-slice1",
        family_id="slice1-family",
        store=InMemoryCallRecordStore(),
        mission=_custom_mission(),
    )
    assert session.uses_dialogue_engine()
    assert session._engine is not None
    session.start()
    # Delivered question for utilities — real answer context (not handcrafted turn).
    engine = session._engine
    hint = "Успели сегодня оплатить коммунальные счета?"
    engine.state.delivered_question = Question(
        question_id="q-util-1",
        slot="utilities_paid",
        goal_id="utilities_paid",
        text=hint,
        phase=QuestionPhase.DELIVERED,
        intent="ask_goal",
    )
    util = engine.state.goals["utilities_paid"]
    util.lifecycle = GoalLifecycle.ASKED
    util.delivered_attempts = 1
    return session


def test_custom_mission_fail_closed_without_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "0")
    with pytest.raises(CustomMissionRequiresDialogueEngine):
        CallSession(
            call_id="no-engine",
            family_id="slice1-family",
            store=InMemoryCallRecordStore(),
            mission=_custom_mission(),
        )


def test_arbitrary_mission_one_turn_via_callsession_understanding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_with_mission(monkeypatch)
    engine = session._engine
    assert engine is not None

    # Production understanding entry (same helper CallActor/kernel path uses).
    rich = build_rich_turn_from_text(
        _UTTERANCE,
        utterance_id="utt-1",
        engine_state=engine.state,
    )
    assert rich.goal_answers, "structured understanding must emit goal_answers"
    assert any(a.goal_id == "utilities_paid" and a.value == "yes" for a in rich.goal_answers)
    assert not any(a.goal_id == "groceries_help" for a in rich.goal_answers)

    result = session.handle_user_text(_UTTERANCE, rich_turn=rich)
    assert result.from_engine is True

    util = engine.state.goals["utilities_paid"]
    assert util.lifecycle == GoalLifecycle.SATISFIED
    assert util.answer == "yes"
    assert util.evidence_ids
    evidence_blob = " ".join(
        str(getattr(engine.state.observations.get(eid), "evidence", "") or eid)
        for eid in util.evidence_ids
    )
    assert "оплат" in evidence_blob.lower() or any(
        "оплат" in (getattr(o, "evidence", "") or "").lower()
        for o in engine.state.observations.values()
    )

    groceries = engine.state.goals["groceries_help"]
    assert groceries.lifecycle != GoalLifecycle.SATISFIED
    assert groceries.answer is None

    # Heating preserved as observation and/or IssueEpisode.
    obs_values = " ".join(
        f"{o.attribute} {o.value} {o.evidence}" for o in engine.state.observations.values()
    ).lower()
    assert "отоплени" in obs_values or any(
        "отоплени" in ep.primary_label.lower()
        or any("отоплени" in (m.label or "").lower() for m in ep.mentions)
        for ep in engine.state.issue_episodes.values()
    )

    # Daughter mention not lost.
    assert "дочь" in obs_values or any(
        "дочь" in (o.value or "").lower() or "дочь" in (o.evidence or "").lower()
        for o in engine.state.observations.values()
    )

    # Must not re-mark utilities as open after apply.
    assert engine.state.goals["utilities_paid"].lifecycle == GoalLifecycle.SATISFIED


def test_side_issue_same_turn_creates_episode_or_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_with_mission(monkeypatch)
    engine = session._engine
    assert engine is not None
    rich = build_rich_turn_from_text(
        _UTTERANCE,
        utterance_id="utt-2",
        engine_state=engine.state,
    )
    session.handle_user_text(_UTTERANCE, rich_turn=rich)
    has_problem_obs = any(
        o.attribute == "reported_problem" and "отоплени" in (o.value or "").lower()
        for o in engine.state.observations.values()
    )
    has_episode = any(
        "отоплени" in ep.primary_label.lower()
        or any("отоплени" in (m.label or "").lower() for m in ep.mentions)
        for ep in engine.state.issue_episodes.values()
    )
    assert has_problem_obs or has_episode


def test_goal_definition_not_collapsed_into_goal_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_with_mission(monkeypatch)
    engine = session._engine
    assert engine is not None
    assert engine.mission.goals[0].prompt_hint
    # Runtime GoalState must not carry prompt_hint (definition stays on catalog).
    runtime = engine.state.goals["utilities_paid"]
    assert not hasattr(runtime, "prompt_hint") or not getattr(runtime, "prompt_hint", None)
    assert engine.state.mission_catalog
    assert engine.state.mission_catalog[0].goal_id == "utilities_paid"
    assert runtime.lifecycle == GoalLifecycle.ASKED


def test_no_mission_specific_symbols_in_understanding_module() -> None:
    from pathlib import Path

    src = Path("packages/dialogue_engine/mission_understanding.py").read_text(encoding="utf-8")
    for banned in (
        "utilities_paid",
        "groceries_help",
        "коммунальн",
        "продукт",
        "отоплени",
    ):
        assert banned not in src, f"mission-specific token leaked: {banned}"
