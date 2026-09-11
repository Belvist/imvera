"""Slice 1 P0 fix: provider boundary + grounding before SATISFIED."""

from __future__ import annotations

import uuid

import pytest

from packages.contracts.semantic import Evidence, IssueMention
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.mission import (
    CallMission,
    CustomMissionRequiresDialogueEngine,
    GoalAnswerCandidate,
    GoalDefinition,
)
from packages.dialogue_engine.mission_grounding import (
    filter_grounded_goal_answers,
    validate_goal_answer_candidate,
)
from packages.dialogue_engine.mission_understanding import (
    MissionUnderstandingRequest,
    StructuredMissionResult,
    reset_mission_understanding_provider,
    set_mission_understanding_provider,
)
from packages.dialogue_engine.semantic_kernel.observation_memory import atomic_semantic_apply
from packages.dialogue_engine.semantic_kernel.types import Observation, SubjectKind
from packages.dialogue_engine.state import GoalLifecycle, Question, QuestionPhase
from packages.dialogue_engine.turn_understanding import (
    RichUserTurn,
    build_rich_turn_from_text,
)

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


class _DemoFakeProvider:
    """Deterministic stand-in for future production semantic model (same schema)."""

    def understand(self, request: MissionUnderstandingRequest) -> StructuredMissionResult:
        text = request.text
        answers: list[GoalAnswerCandidate] = []
        if "оплатил" in text.lower() and any(
            g.goal_id == "utilities_paid" for g in request.mission.goals
        ):
            answers.append(
                GoalAnswerCandidate(
                    goal_id="utilities_paid",
                    value="yes",
                    confidence=0.97,
                    evidence="утром оплатил",
                )
            )
        obs: list[Observation] = []
        mentions: list[IssueMention] = []
        if "отопление" in text.lower():
            clause = "отопление опять еле работает"
            oid = f"obs-{uuid.uuid4().hex[:8]}"
            obs.append(
                Observation(
                    observation_id=oid,
                    attribute="reported_problem",
                    value=clause,
                    normalized_value=clause.lower(),
                    subject=SubjectKind.SPEAKER,
                    confidence=0.9,
                    evidence=clause,
                    status="candidate",
                )
            )
            start = text.lower().find(clause)
            mentions.append(
                IssueMention(
                    mention_id=f"im-{oid[-8:]}",
                    kind="other",
                    label=clause,
                    role="primary",
                    body_site=None,
                    temporal_scope="now",
                    status="active",
                    onset=None,
                    severity=None,
                    evidence=Evidence(
                        start=max(0, start),
                        end=max(0, start) + len(clause),
                        quote=clause,
                    ),
                )
            )
        if "дочь" in text.lower():
            clause = "дочь вечером обещала зайти"
            obs.append(
                Observation(
                    observation_id=f"obs-{uuid.uuid4().hex[:8]}",
                    attribute="other_person_plan",
                    value=clause,
                    normalized_value=clause.lower(),
                    subject=SubjectKind.OTHER_PERSON,
                    confidence=0.88,
                    evidence=clause,
                    status="candidate",
                )
            )
        return StructuredMissionResult(
            goal_answers=tuple(answers),
            observations=tuple(obs),
            issue_mentions=tuple(mentions),
        )


class _DualAnswerFakeProvider:
    """Adversarial: one utterance → two goal answers. No A/B Python in engine."""

    def understand(self, request: MissionUnderstandingRequest) -> StructuredMissionResult:
        return StructuredMissionResult(
            goal_answers=(
                GoalAnswerCandidate(
                    goal_id="worker_visited",
                    value="yes",
                    confidence=0.96,
                    evidence="мастер приходил",
                ),
                GoalAnswerCandidate(
                    goal_id="repair_completed",
                    value="no",
                    confidence=0.95,
                    evidence="кран он так и не починил",
                ),
            )
        )


@pytest.fixture(autouse=True)
def _reset_provider() -> None:
    reset_mission_understanding_provider()
    yield
    reset_mission_understanding_provider()


def _session_with_mission(
    monkeypatch: pytest.MonkeyPatch,
    mission: CallMission | None = None,
) -> CallSession:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    mission = mission or _custom_mission()
    session = CallSession(
        call_id="mission-slice1",
        family_id="slice1-family",
        store=InMemoryCallRecordStore(),
        mission=mission,
    )
    assert session.uses_dialogue_engine()
    assert session._engine is not None
    session.start()
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


def test_arbitrary_mission_via_provider_and_callsession(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_mission_understanding_provider(_DemoFakeProvider())
    session = _session_with_mission(monkeypatch)
    engine = session._engine
    assert engine is not None
    engine.state.delivered_question = Question(
        question_id="q-util-1",
        slot="utilities_paid",
        goal_id="utilities_paid",
        text="Успели сегодня оплатить коммунальные счета?",
        phase=QuestionPhase.DELIVERED,
        intent="ask_goal",
    )
    engine.state.goals["utilities_paid"].lifecycle = GoalLifecycle.ASKED

    rich = build_rich_turn_from_text(
        _UTTERANCE,
        utterance_id="utt-1",
        engine_state=engine.state,
    )
    assert any(a.goal_id == "utilities_paid" and a.value == "yes" for a in rich.goal_answers)
    assert not any(a.goal_id == "groceries_help" for a in rich.goal_answers)

    result = session.handle_user_text(_UTTERANCE, rich_turn=rich)
    assert result.from_engine is True

    util = engine.state.goals["utilities_paid"]
    assert util.lifecycle == GoalLifecycle.SATISFIED
    assert util.answer == "yes"
    assert util.evidence_ids

    groceries = engine.state.goals["groceries_help"]
    assert groceries.lifecycle != GoalLifecycle.SATISFIED

    obs_blob = " ".join(
        f"{o.attribute} {o.value} {o.evidence}" for o in engine.state.observations.values()
    ).lower()
    assert "отоплени" in obs_blob
    assert "дочь" in obs_blob


def test_adversarial_two_goal_answers_same_utterance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission = CallMission(
        mission_id="repair-check",
        goals=(
            GoalDefinition(
                goal_id="worker_visited",
                prompt_hint="Мастер сегодня приходил?",
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
                priority=1,
            ),
            GoalDefinition(
                goal_id="repair_completed",
                prompt_hint="Кран починили?",
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
                priority=2,
            ),
        ),
    )
    set_mission_understanding_provider(_DualAnswerFakeProvider())
    session = _session_with_mission(monkeypatch, mission=mission)
    engine = session._engine
    assert engine is not None
    engine.state.delivered_question = Question(
        question_id="q-a",
        slot="worker_visited",
        goal_id="worker_visited",
        text="Мастер сегодня приходил?",
        phase=QuestionPhase.DELIVERED,
        intent="ask_goal",
    )
    engine.state.goals["worker_visited"].lifecycle = GoalLifecycle.ASKED

    user = "Да, мастер приходил, но кран он так и не починил."
    rich = build_rich_turn_from_text(
        user, utterance_id="utt-dual", engine_state=engine.state
    )
    assert {a.goal_id: a.value for a in rich.goal_answers} == {
        "worker_visited": "yes",
        "repair_completed": "no",
    }
    session.handle_user_text(user, rich_turn=rich)
    assert engine.state.goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED
    assert engine.state.goals["worker_visited"].answer == "yes"
    assert engine.state.goals["repair_completed"].lifecycle == GoalLifecycle.SATISFIED
    assert engine.state.goals["repair_completed"].answer == "no"


def test_fast_path_bare_yes_only_for_delivered_goal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without semantic provider: only bare да/нет/не знаю bind to delivered goal."""
    session = _session_with_mission(monkeypatch)
    engine = session._engine
    assert engine is not None
    engine.state.delivered_question = Question(
        question_id="q1",
        slot="utilities_paid",
        goal_id="utilities_paid",
        text="Успели оплатить?",
        phase=QuestionPhase.DELIVERED,
        intent="ask_goal",
    )
    engine.state.goals["utilities_paid"].lifecycle = GoalLifecycle.ASKED

    rich_long = build_rich_turn_from_text(
        _UTTERANCE, utterance_id="u-long", engine_state=engine.state
    )
    assert rich_long.goal_answers == ()

    rich_yes = build_rich_turn_from_text(
        "Да", utterance_id="u-yes", engine_state=engine.state
    )
    assert len(rich_yes.goal_answers) == 1
    assert rich_yes.goal_answers[0].goal_id == "utilities_paid"
    assert rich_yes.goal_answers[0].value == "yes"


def test_grounding_rejects_invalid_enum_and_hallucinated_evidence() -> None:
    mission = _custom_mission()
    utterance = "Да, утром оплатил."
    bad_enum = GoalAnswerCandidate(
        goal_id="utilities_paid",
        value="probably_tomorrow",
        confidence=0.99,
        evidence="утром оплатил",
    )
    ok, reason = validate_goal_answer_candidate(
        bad_enum, mission=mission, utterance=utterance
    )
    assert ok is False
    assert reason == "value_not_in_allowed_values"

    hallucinated = GoalAnswerCandidate(
        goal_id="utilities_paid",
        value="yes",
        confidence=0.99,
        evidence="несуществующая цитата",
    )
    ok2, reason2 = validate_goal_answer_candidate(
        hallucinated, mission=mission, utterance=utterance
    )
    assert ok2 is False
    assert reason2 == "evidence_not_grounded"

    unknown = GoalAnswerCandidate(
        goal_id="not_in_mission",
        value="yes",
        confidence=0.9,
        evidence="утром оплатил",
    )
    ok3, reason3 = validate_goal_answer_candidate(
        unknown, mission=mission, utterance=utterance
    )
    assert ok3 is False
    assert reason3 == "unknown_goal_id"

    good = GoalAnswerCandidate(
        goal_id="utilities_paid",
        value="yes",
        confidence=0.9,
        evidence="утром оплатил",
    )
    assert validate_goal_answer_candidate(good, mission=mission, utterance=utterance)[0]


def test_invalid_candidates_do_not_satisfy_via_atomic_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_with_mission(monkeypatch)
    engine = session._engine
    assert engine is not None
    turn = RichUserTurn(
        utterance_id="bad-1",
        raw_text="Да, утром оплатил.",
        dialogue_act="answer",
        control="none",
        answers_pending_question=True,
        needs_clarification=False,
        goal_answers=(
            GoalAnswerCandidate(
                goal_id="utilities_paid",
                value="probably_tomorrow",
                confidence=0.99,
                evidence="утром оплатил",
            ),
            GoalAnswerCandidate(
                goal_id="utilities_paid",
                value="yes",
                confidence=0.99,
                evidence="выдуманный фрагмент",
            ),
        ),
    )
    atomic_semantic_apply(engine.state, turn)
    assert engine.state.goals["utilities_paid"].lifecycle != GoalLifecycle.SATISFIED


def test_two_valid_answers_and_side_issue_via_atomic_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission = CallMission(
        mission_id="dual",
        goals=(
            GoalDefinition(
                goal_id="worker_visited",
                prompt_hint="Мастер приходил?",
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
            ),
            GoalDefinition(
                goal_id="repair_completed",
                prompt_hint="Починили?",
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
            ),
        ),
    )
    session = _session_with_mission(monkeypatch, mission=mission)
    engine = session._engine
    assert engine is not None
    utterance = "Да, мастер приходил, но кран он так и не починил."
    heating = "отопление еле работает"
    turn = RichUserTurn(
        utterance_id="ok-1",
        raw_text=utterance + " " + heating,
        dialogue_act="answer",
        control="none",
        answers_pending_question=True,
        needs_clarification=False,
        goal_answers=(
            GoalAnswerCandidate(
                goal_id="worker_visited",
                value="yes",
                confidence=0.9,
                evidence="мастер приходил",
            ),
            GoalAnswerCandidate(
                goal_id="repair_completed",
                value="no",
                confidence=0.9,
                evidence="кран он так и не починил",
            ),
        ),
        observations=(
            Observation(
                observation_id="obs-heat",
                attribute="reported_problem",
                value=heating,
                evidence=heating,
                subject=SubjectKind.SPEAKER,
                status="candidate",
            ),
        ),
        issue_mentions=(
            IssueMention(
                mention_id="im-heat",
                kind="other",
                label=heating,
                role="primary",
                body_site=None,
                temporal_scope="now",
                status="active",
                onset=None,
                severity=None,
                evidence=Evidence(start=0, end=len(heating), quote=heating),
            ),
        ),
    )
    atomic_semantic_apply(engine.state, turn)
    assert engine.state.goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED
    assert engine.state.goals["repair_completed"].lifecycle == GoalLifecycle.SATISFIED
    assert engine.state.goals["repair_completed"].answer == "no"
    assert any(
        "отоплени" in (o.value or "").lower() for o in engine.state.observations.values()
    ) or any(
        "отоплени" in ep.primary_label.lower()
        or any("отоплени" in (m.label or "").lower() for m in ep.mentions)
        for ep in engine.state.issue_episodes.values()
    )


def test_filter_keeps_multiple_grounded_answers() -> None:
    mission = CallMission(
        mission_id="m",
        goals=(
            GoalDefinition(
                goal_id="a",
                answer_type="enum",
                allowed_values=("yes", "no"),
            ),
            GoalDefinition(
                goal_id="b",
                answer_type="enum",
                allowed_values=("yes", "no"),
            ),
        ),
    )
    utterance = "alpha_yes было, beta_no не было"
    kept = filter_grounded_goal_answers(
        (
            GoalAnswerCandidate(
                goal_id="a", value="yes", confidence=0.9, evidence="alpha_yes"
            ),
            GoalAnswerCandidate(
                goal_id="b", value="no", confidence=0.9, evidence="beta_no"
            ),
        ),
        mission=mission,
        utterance=utterance,
    )
    assert {c.goal_id: c.value for c in kept} == {"a": "yes", "b": "no"}


def test_no_domain_regex_dictionary_in_understanding_module() -> None:
    from pathlib import Path

    src = Path("packages/dialogue_engine/mission_understanding.py").read_text(
        encoding="utf-8"
    )
    for banned in (
        "оплатил",
        "приходил",
        "заплатил",
        "слома",
        "еле работает",
        "не работает",
        "utilities_paid",
        "worker_visited",
    ):
        assert banned not in src, f"domain/mission token leaked: {banned}"


def test_fast_path_refusal_is_not_factual_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Не хочу про это говорить» must not SATISFY goal as answer=no."""
    mission = CallMission(
        mission_id="eat-check",
        goals=(
            GoalDefinition(
                goal_id="ate_today",
                prompt_hint="Сегодня удалось поесть?",
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
            ),
        ),
    )
    session = _session_with_mission(monkeypatch, mission=mission)
    engine = session._engine
    assert engine is not None
    engine.state.delivered_question = Question(
        question_id="q-eat",
        slot="ate_today",
        goal_id="ate_today",
        text="Сегодня удалось поесть?",
        phase=QuestionPhase.DELIVERED,
        intent="ask_goal",
    )
    engine.state.goals["ate_today"].lifecycle = GoalLifecycle.ASKED

    rich = build_rich_turn_from_text(
        "Не хочу про это говорить.",
        utterance_id="u-refuse",
        engine_state=engine.state,
    )
    assert rich.goal_answers == ()
    session.handle_user_text("Не хочу про это говорить.", rich_turn=rich)
    goal = engine.state.goals["ate_today"]
    assert goal.lifecycle != GoalLifecycle.SATISFIED
    assert goal.answer != "no"


def test_goal_definition_not_collapsed_into_goal_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_with_mission(monkeypatch)
    engine = session._engine
    assert engine is not None
    runtime = engine.state.goals["utilities_paid"]
    assert not hasattr(runtime, "prompt_hint") or not getattr(runtime, "prompt_hint", None)
    assert engine.state.mission_catalog[0].goal_id == "utilities_paid"
