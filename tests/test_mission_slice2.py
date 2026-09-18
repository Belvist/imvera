"""Slice 2: custom CallMission owns full call flow on existing DialogueEngine."""

from __future__ import annotations

import uuid

import pytest

from packages.contracts.semantic import Evidence, IssueMention
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.conversation_policy import TurnContext, schedule_next_action
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.mission import (
    CallMission,
    GoalAnswerCandidate,
    GoalDefinition,
    GoalDispositionCandidate,
)
from packages.dialogue_engine.mission_understanding import (
    FastPathMissionProvider,
    MissionUnderstandingRequest,
    StructuredMissionResult,
    reset_mission_understanding_provider,
    set_mission_understanding_provider,
)
from packages.dialogue_engine.semantic_kernel.types import Observation, SubjectKind
from packages.dialogue_engine.state import GoalLifecycle, QuestionPhase
from packages.dialogue_engine.turn_understanding import RichUserTurn, build_rich_turn_from_text


def _home_mission() -> CallMission:
    return CallMission(
        mission_id="home-repair-slice2",
        goals=(
            GoalDefinition(
                goal_id="worker_visited",
                prompt_hint="Мастер сегодня приходил?",
                required=True,
                priority=10,
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
                max_attempts=2,
            ),
            GoalDefinition(
                goal_id="repair_completed",
                prompt_hint="Он починил кран?",
                required=True,
                priority=20,
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
                max_attempts=2,
            ),
            GoalDefinition(
                goal_id="groceries_help",
                prompt_hint="Нужна помощь с продуктами?",
                required=True,
                priority=30,
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
                max_attempts=2,
            ),
        ),
    )


class _Slice2FakeProvider:
    """Deterministic stand-in for production semantic model (same schema)."""

    def understand(self, request: MissionUnderstandingRequest) -> StructuredMissionResult:
        text = request.text
        low = text.lower()
        answers: list[GoalAnswerCandidate] = []
        dispositions: list[GoalDispositionCandidate] = []
        obs: list[Observation] = []
        mentions: list[IssueMention] = []
        user_q: str | None = None
        control = "none"

        if "не хочу про еду" in low or "не хочу про это" in low:
            gid = request.delivered_goal_id or "ate_today"
            dispositions.append(
                GoalDispositionCandidate(
                    goal_id=gid,
                    disposition="declined",
                    confidence=0.95,
                    evidence="Не хочу про еду говорить"
                    if "еду" in low
                    else "Не хочу про это говорить",
                )
            )
        if "не хочу разговаривать" in low or "не хочу говорить" in low:
            control = "stop_call"

        if "перепутал" in low and "не приходил" in low:
            answers.append(
                GoalAnswerCandidate(
                    goal_id="worker_visited",
                    value="no",
                    confidence=0.96,
                    evidence="сегодня он не приходил",
                    is_correction=True,
                )
            )
        elif "приходил" in low and "мастер" not in low:
            # «Да, приходил…»
            if "да" in low or "приходил" in low:
                answers.append(
                    GoalAnswerCandidate(
                        goal_id="worker_visited",
                        value="yes",
                        confidence=0.96,
                        evidence="приходил",
                    )
                )
        if "мастер приходил" in low or (
            "да, приходил" in low or low.strip().startswith("да, приходил")
        ):
            if not any(a.goal_id == "worker_visited" for a in answers):
                answers.append(
                    GoalAnswerCandidate(
                        goal_id="worker_visited",
                        value="yes",
                        confidence=0.96,
                        evidence="приходил",
                    )
                )

        if "кран" in low and ("не починил" in low or "не починили" in low):
            answers.append(
                GoalAnswerCandidate(
                    goal_id="repair_completed",
                    value="no",
                    confidence=0.95,
                    evidence="кран он не починил"
                    if "кран он не починил" in low
                    else "не починил",
                )
            )
        if "починил кран" in low or "кран починил" in low:
            answers.append(
                GoalAnswerCandidate(
                    goal_id="repair_completed",
                    value="yes",
                    confidence=0.95,
                    evidence="починил",
                )
            )

        if "продукты" in low and ("дочь" in low or "принесла" in low or "принесли" in low):
            answers.append(
                GoalAnswerCandidate(
                    goal_id="groceries_help",
                    value="no",
                    confidence=0.94,
                    evidence="продукты дочь уже принесла"
                    if "продукты дочь уже принесла" in low
                    else "принесла",
                )
            )
            obs.append(
                Observation(
                    observation_id=f"obs-{uuid.uuid4().hex[:8]}",
                    attribute="other_person_plan",
                    value="дочь уже принесла продукты",
                    normalized_value="дочь уже принесла продукты",
                    subject=SubjectKind.OTHER_PERSON,
                    confidence=0.9,
                    evidence="дочь уже принесла",
                    status="candidate",
                )
            )

        if "батаре" in low or "отоплен" in low or "не гре" in low:
            clause = "батареи опять почти не греют"
            if "батареи опять почти не греют" not in low:
                clause = "батареи"
            start = low.find(clause[:8]) if clause[:8] in low else 0
            quote = text[start : start + len(clause)] if start >= 0 else clause
            oid = f"obs-{uuid.uuid4().hex[:8]}"
            obs.append(
                Observation(
                    observation_id=oid,
                    attribute="reported_problem",
                    value=quote,
                    normalized_value=quote.lower(),
                    subject=SubjectKind.SPEAKER,
                    confidence=0.9,
                    evidence=quote,
                    status="candidate",
                )
            )
            mentions.append(
                IssueMention(
                    mention_id=f"im-{oid[-8:]}",
                    kind="other",
                    label=quote,
                    role="primary",
                    body_site=None,
                    temporal_scope="now",
                    status="active",
                    onset=None,
                    severity=None,
                    evidence=Evidence(
                        start=max(0, start),
                        end=max(0, start) + max(1, len(quote)),
                        quote=quote,
                    ),
                )
            )

        if "кто" in low and ("ты" in low or "вы" in low):
            user_q = text.strip()

        return StructuredMissionResult(
            goal_answers=tuple(answers),
            goal_dispositions=tuple(dispositions),
            observations=tuple(obs),
            issue_mentions=tuple(mentions),
            user_question=user_q,
            control=control,
        )


@pytest.fixture(autouse=True)
def _reset_provider() -> None:
    reset_mission_understanding_provider()
    yield
    reset_mission_understanding_provider()


def _engine(mission: CallMission | None = None, provider=None) -> DialogueEngine:
    return DialogueEngine(
        call_id="slice2-call",
        elder_display_name="Анной Петровной",
        mission=mission or _home_mission(),
        mission_understanding_provider=provider,
    )


def _deliver(eng: DialogueEngine) -> str:
    speak = eng.pop_speak_effect()
    assert speak is not None
    eng.on_playout_completed(speak.generation, speak.question_id)
    return speak.text


def _turn(
    eng: DialogueEngine,
    text: str,
    *,
    uid: str,
    provider=None,
    **updates,
) -> RichUserTurn:
    active = provider if provider is not None else eng.mission_understanding_provider
    if active is not None:
        set_mission_understanding_provider(active)  # type: ignore[arg-type]
    rich = build_rich_turn_from_text(
        text,
        utterance_id=uid,
        engine_state=eng.state,
        mission_provider=active,
    )
    if updates:
        rich = rich.model_copy(update=updates)
    return rich


def test_custom_opening_asks_first_mission_goal_not_wellness() -> None:
    eng = _engine()
    effects = eng.start()
    assert effects
    text = _deliver(eng)
    assert "Мастер сегодня приходил?" in text
    assert "Как вы себя чувствуете" not in text
    assert eng.state.goals["worker_visited"].lifecycle in {
        GoalLifecycle.ACTIVE,
        GoalLifecycle.ANSWER_PENDING,
        GoalLifecycle.ASKED,
    }
    assert eng.state.delivered_question is not None
    assert eng.state.delivered_question.goal_id == "worker_visited"


def test_cancelled_question_does_not_bind_fast_path_yes() -> None:
    eng = _engine()
    eng.start()
    speak = eng.pop_speak_effect()
    assert speak is not None
    eng.on_playout_cancelled(speak.generation, speak.question_id)
    assert eng.state.playing_question is None or (
        eng.state.playing_question
        and eng.state.playing_question.phase == QuestionPhase.CANCELLED
    )
    eng.state.delivered_question = None
    rich = build_rich_turn_from_text(
        "да",
        utterance_id="barge-yes",
        engine_state=eng.state,
        mission_provider=FastPathMissionProvider(),
    )
    assert rich.goal_answers == ()
    eng.on_user_turn("barge-yes", "да", rich_turn=rich)
    assert eng.state.goals["worker_visited"].lifecycle != GoalLifecycle.SATISFIED


def test_delivered_yes_satisfies_then_second_goal() -> None:
    set_mission_understanding_provider(_Slice2FakeProvider())
    eng = _engine(provider=_Slice2FakeProvider())
    eng.start()
    _deliver(eng)
    rich = _turn(eng, "Да, приходил.", uid="u1")
    assert any(a.goal_id == "worker_visited" and a.value == "yes" for a in rich.goal_answers)
    eng.on_user_turn("u1", "Да, приходил.", rich_turn=rich)
    assert eng.state.goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED
    text = _deliver(eng)
    assert "Он починил кран?" in text
    assert eng.state.goals["repair_completed"].lifecycle != GoalLifecycle.SATISFIED


def test_two_goals_one_turn_neither_repeated() -> None:
    set_mission_understanding_provider(_Slice2FakeProvider())
    eng = _engine(provider=_Slice2FakeProvider())
    eng.start()
    _deliver(eng)
    user = "Да, приходил, кран он не починил."
    # Ensure dual answers with grounded evidence present in utterance.
    rich = RichUserTurn(
        utterance_id="dual",
        raw_text=user,
        dialogue_act="answer",
        control="none",
        answers_pending_question=True,
        needs_clarification=False,
        goal_answers=(
            GoalAnswerCandidate(
                goal_id="worker_visited",
                value="yes",
                confidence=0.96,
                evidence="приходил",
            ),
            GoalAnswerCandidate(
                goal_id="repair_completed",
                value="no",
                confidence=0.95,
                evidence="кран он не починил",
            ),
        ),
    )
    eng.on_user_turn("dual", user, rich_turn=rich)
    assert eng.state.goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED
    assert eng.state.goals["repair_completed"].lifecycle == GoalLifecycle.SATISFIED
    text = _deliver(eng)
    assert "Мастер сегодня приходил?" not in text
    assert "Он починил кран?" not in text
    assert "продукт" in text.lower()


def test_side_issue_suspend_household_help_resume_exact_goal() -> None:
    set_mission_understanding_provider(_Slice2FakeProvider())
    eng = _engine(provider=_Slice2FakeProvider())
    eng.start()
    _deliver(eng)
    # Interrupt without answering mission goal
    user = "Батареи опять почти не греют."
    rich = _turn(eng, user, uid="heat")
    assert rich.issue_mentions
    eng.on_user_turn("heat", user, rich_turn=rich)
    assert eng.state.suspended_obligation is not None
    assert eng.state.suspended_obligation.goal_id == "worker_visited"
    help_q = _deliver(eng)
    assert "помощь" in help_q.lower() or "справляетесь" in help_q.lower()
    assert "сильно" not in help_q.lower()
    assert "как давно" not in help_q.lower()

    eng.on_user_turn(
        "ok",
        "Пока справлюсь сам.",
        rich_turn=RichUserTurn(
            utterance_id="ok",
            raw_text="Пока справлюсь сам.",
            dialogue_act="answer",
            control="none",
            answers_pending_question=True,
            needs_clarification=False,
        ),
    )
    resume = _deliver(eng)
    assert "Мастер сегодня приходил?" in resume
    assert eng.state.goals["worker_visited"].lifecycle != GoalLifecycle.SATISFIED


def test_non_health_issue_never_gets_severity_onset() -> None:
    from packages.dialogue_engine.semantic_kernel.information_gain import best_question_need
    from packages.dialogue_engine.state import IssueEpisode

    eng = _engine()
    ep = IssueEpisode(
        episode_id="ep-other",
        kind="other",
        primary_label="сломался кран",
        status="open",
    )
    eng.state.issue_episodes[ep.episode_id] = ep
    need = best_question_need(eng.state, ep)
    assert need is not None
    assert need.attribute == "needs_help"


def test_user_question_answer_and_resume_same_turn() -> None:
    set_mission_understanding_provider(_Slice2FakeProvider())
    eng = _engine(provider=_Slice2FakeProvider())
    eng.start()
    _deliver(eng)
    # Satisfy first, ask second
    eng.on_user_turn(
        "a1",
        "Да, приходил.",
        rich_turn=RichUserTurn(
            utterance_id="a1",
            raw_text="Да, приходил.",
            dialogue_act="answer",
            control="none",
            answers_pending_question=True,
            needs_clarification=False,
            goal_answers=(
                GoalAnswerCandidate(
                    goal_id="worker_visited",
                    value="yes",
                    confidence=0.96,
                    evidence="приходил",
                ),
            ),
        ),
    )
    _deliver(eng)
    rich = _turn(eng, "А ты вообще кто?", uid="who")
    assert rich.user_question
    eng.on_user_turn("who", "А ты вообще кто?", rich_turn=rich)
    text = _deliver(eng)
    assert "Вера" in text
    assert "Он починил кран?" in text


def test_answer_plus_user_question_advances_to_next_goal() -> None:
    eng = _engine(provider=_Slice2FakeProvider())
    eng.start()
    _deliver(eng)
    user = "Да, приходил. А ты вообще кто?"
    rich = RichUserTurn(
        utterance_id="aq",
        raw_text=user,
        dialogue_act="answer",
        control="none",
        answers_pending_question=True,
        needs_clarification=False,
        user_question="А ты вообще кто?",
        goal_answers=(
            GoalAnswerCandidate(
                goal_id="worker_visited",
                value="yes",
                confidence=0.96,
                evidence="приходил",
            ),
        ),
    )
    eng.on_user_turn("aq", user, rich_turn=rich)
    assert eng.state.goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED
    text = _deliver(eng)
    assert "Вера" in text
    assert "Он починил кран?" in text
    assert "Мастер сегодня приходил?" not in text


def test_goal_refusal_declined_no_repeat() -> None:
    mission = CallMission(
        mission_id="eat",
        goals=(
            GoalDefinition(
                goal_id="ate_today",
                prompt_hint="Сегодня удалось нормально поесть?",
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
            ),
            GoalDefinition(
                goal_id="mood_ok",
                prompt_hint="Как настроение?",
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
                priority=20,
            ),
        ),
    )
    provider = _Slice2FakeProvider()
    eng = _engine(mission=mission, provider=provider)
    eng.start()
    _deliver(eng)
    user = "Не хочу про еду говорить."
    rich = RichUserTurn(
        utterance_id="ref",
        raw_text=user,
        dialogue_act="answer",
        control="none",
        answers_pending_question=True,
        needs_clarification=False,
        goal_dispositions=(
            GoalDispositionCandidate(
                goal_id="ate_today",
                disposition="declined",
                confidence=0.95,
                evidence="Не хочу про еду говорить",
            ),
        ),
    )
    eng.on_user_turn("ref", user, rich_turn=rich)
    assert eng.state.goals["ate_today"].lifecycle == GoalLifecycle.DECLINED
    text = _deliver(eng)
    assert "поесть" not in text.lower()
    assert "настроение" in text.lower()


def test_call_refusal_control_close() -> None:
    eng = _engine()
    eng.start()
    _deliver(eng)
    rich = RichUserTurn(
        utterance_id="stop",
        raw_text="Не хочу разговаривать.",
        dialogue_act="control",
        control="stop_call",
        answers_pending_question=False,
        needs_clarification=False,
    )
    effects = eng.on_user_turn("stop", "Не хочу разговаривать.", rich_turn=rich)
    assert eng.state.call_closed or any(
        getattr(e, "intent", "") in {"goodbye", "goodbye_final", "summary"}
        or e.__class__.__name__ == "EndCallEffect"
        for e in effects
    ) or eng.state.fsm_state.value in {"GOODBYE", "SUMMARY", "FINAL_CLASSIFICATION"}


def test_goal_correction_supersedes_previous_truth() -> None:
    eng = _engine(provider=_Slice2FakeProvider())
    eng.start()
    _deliver(eng)
    eng.on_user_turn(
        "y",
        "Да, приходил.",
        rich_turn=RichUserTurn(
            utterance_id="y",
            raw_text="Да, приходил.",
            dialogue_act="answer",
            control="none",
            answers_pending_question=True,
            needs_clarification=False,
            goal_answers=(
                GoalAnswerCandidate(
                    goal_id="worker_visited",
                    value="yes",
                    confidence=0.96,
                    evidence="приходил",
                ),
            ),
        ),
    )
    assert eng.state.goals["worker_visited"].answer == "yes"
    _deliver(eng)
    # Accidental non-correction must not overwrite
    eng.on_user_turn(
        "bad",
        "Нет.",
        rich_turn=RichUserTurn(
            utterance_id="bad",
            raw_text="Нет.",
            dialogue_act="answer",
            control="none",
            answers_pending_question=True,
            needs_clarification=False,
            goal_answers=(
                GoalAnswerCandidate(
                    goal_id="worker_visited",
                    value="no",
                    confidence=0.9,
                    evidence="Нет",
                    is_correction=False,
                ),
            ),
        ),
    )
    assert eng.state.goals["worker_visited"].answer == "yes"
    eng.on_user_turn(
        "corr",
        "Нет, я перепутал, сегодня он не приходил.",
        rich_turn=RichUserTurn(
            utterance_id="corr",
            raw_text="Нет, я перепутал, сегодня он не приходил.",
            dialogue_act="correction",
            control="none",
            answers_pending_question=False,
            needs_clarification=False,
            correction=True,
            goal_answers=(
                GoalAnswerCandidate(
                    goal_id="worker_visited",
                    value="no",
                    confidence=0.96,
                    evidence="сегодня он не приходил",
                    is_correction=True,
                ),
            ),
        ),
    )
    assert eng.state.goals["worker_visited"].answer == "no"
    assert eng.state.goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED


def test_custom_mission_cannot_enter_frozen_v8(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "soft")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_CUTOVER", "1")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_SOFT_PERCENT", "100")
    eng = _engine()
    eng.start()
    _deliver(eng)

    def boom_legacy(state, turn_context):
        raise AssertionError("legacy should still run for custom, but via bypass")

    # Custom must call legacy path (generalized conversation_policy), never v8 soft.
    from packages.dialogue_engine import decision_router as dr

    calls: list[str] = []

    real_auth = dr._run_authoritative_policy

    def spy_auth(*a, **k):
        calls.append("v8")
        return real_auth(*a, **k)

    monkeypatch.setattr(dr, "_run_authoritative_policy", spy_auth)
    plan = schedule_next_action(
        eng.state,
        TurnContext(
            turn=RichUserTurn(
                utterance_id="x",
                raw_text="угу",
                dialogue_act="answer",
                control="none",
                answers_pending_question=True,
                needs_clarification=False,
            ),
            user_text="угу",
        ),
    )
    assert "v8" not in calls
    assert eng.state.action_policy_router_stats.get("custom_mission_bypass_v8", 0) >= 1
    assert plan.intent in {"ask_mission_goal", "resume_mission_goal", "mission_final_open"} or (
        plan.slot in eng.state.mission_goal_ids
    )


def test_provider_di_on_engine_not_global_required() -> None:
    provider = _Slice2FakeProvider()
    eng = _engine(provider=provider)
    eng.start()
    _deliver(eng)
    reset_mission_understanding_provider()  # clear global
    rich = eng.build_rich_turn("Да, приходил.", utterance_id="di-1")
    assert any(a.goal_id == "worker_visited" for a in rich.goal_answers)


def test_mandatory_e2e_home_mission_trace() -> None:
    """Full multi-turn trace from Slice 2 brief."""
    provider = _Slice2FakeProvider()
    eng = _engine(provider=provider)
    set_mission_understanding_provider(provider)
    eng.start()
    opening = _deliver(eng)
    assert "Мастер сегодня приходил?" in opening

    u1 = "Да, приходил, но батареи опять почти не греют."
    rich1 = RichUserTurn(
        utterance_id="t1",
        raw_text=u1,
        dialogue_act="answer",
        control="none",
        answers_pending_question=True,
        needs_clarification=False,
        goal_answers=(
            GoalAnswerCandidate(
                goal_id="worker_visited",
                value="yes",
                confidence=0.96,
                evidence="приходил",
            ),
        ),
        issue_mentions=(
            IssueMention(
                mention_id="im-heat",
                kind="other",
                label="батареи опять почти не греют",
                role="primary",
                body_site=None,
                temporal_scope="now",
                status="active",
                onset=None,
                severity=None,
                evidence=Evidence(start=24, end=54, quote="батареи опять почти не греют"),
            ),
        ),
        observations=(
            Observation(
                observation_id="obs-heat",
                attribute="reported_problem",
                value="батареи опять почти не греют",
                normalized_value="батареи опять почти не греют",
                subject=SubjectKind.SPEAKER,
                confidence=0.9,
                evidence="батареи опять почти не греют",
                status="candidate",
            ),
        ),
    )
    eng.on_user_turn("t1", u1, rich_turn=rich1)
    assert eng.state.goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED
    assert eng.state.goals["worker_visited"].answer == "yes"
    assert eng.state.goals["repair_completed"].lifecycle != GoalLifecycle.SATISFIED
    assert eng.state.goals["groceries_help"].lifecycle != GoalLifecycle.SATISFIED
    assert eng.state.issue_episodes
    help_q = _deliver(eng)
    assert "помощь" in help_q.lower() or "справляетесь" in help_q.lower()

    eng.on_user_turn(
        "t2",
        "Пока справлюсь сам.",
        rich_turn=RichUserTurn(
            utterance_id="t2",
            raw_text="Пока справлюсь сам.",
            dialogue_act="answer",
            control="none",
            answers_pending_question=True,
            needs_clarification=False,
        ),
    )
    repair_q = _deliver(eng)
    assert "Он починил кран?" in repair_q

    eng.on_user_turn(
        "t3",
        "А ты вообще кто?",
        rich_turn=RichUserTurn(
            utterance_id="t3",
            raw_text="А ты вообще кто?",
            dialogue_act="question",
            control="none",
            answers_pending_question=False,
            needs_clarification=False,
            user_question="А ты вообще кто?",
        ),
    )
    id_resume = _deliver(eng)
    assert "Вера" in id_resume
    assert "Он починил кран?" in id_resume

    u4 = "Кран он не починил. А продукты дочь уже принесла."
    eng.on_user_turn(
        "t4",
        u4,
        rich_turn=RichUserTurn(
            utterance_id="t4",
            raw_text=u4,
            dialogue_act="answer",
            control="none",
            answers_pending_question=True,
            needs_clarification=False,
            goal_answers=(
                GoalAnswerCandidate(
                    goal_id="repair_completed",
                    value="no",
                    confidence=0.95,
                    evidence="Кран он не починил",
                ),
                GoalAnswerCandidate(
                    goal_id="groceries_help",
                    value="no",
                    confidence=0.94,
                    evidence="продукты дочь уже принесла",
                ),
            ),
            observations=(
                Observation(
                    observation_id="obs-daughter",
                    attribute="other_person_plan",
                    value="дочь уже принесла продукты",
                    normalized_value="дочь уже принесла продукты",
                    subject=SubjectKind.OTHER_PERSON,
                    confidence=0.9,
                    evidence="дочь уже принесла",
                    status="candidate",
                ),
            ),
        ),
    )
    assert eng.state.goals["repair_completed"].answer == "no"
    assert eng.state.goals["groceries_help"].lifecycle == GoalLifecycle.SATISFIED
    final_q = _deliver(eng)
    assert "добавить" in final_q.lower() or "ещё" in final_q.lower()
    assert "продукт" not in final_q.lower()

    eng.on_user_turn(
        "t5",
        "Нет, больше ничего.",
        rich_turn=RichUserTurn(
            utterance_id="t5",
            raw_text="Нет, больше ничего.",
            dialogue_act="answer",
            control="none",
            answers_pending_question=True,
            needs_clarification=False,
        ),
    )
    close_text = ""
    speak = eng.pop_speak_effect()
    if speak:
        close_text = speak.text
        eng.on_playout_completed(speak.generation, speak.question_id)
    assert eng.state.important_to_share_resolved or eng.state.call_closed or close_text


def test_daily_check_opening_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    from packages.dialogue_engine.mission import daily_check_mission

    session = CallSession(
        call_id="daily-reg",
        family_id="slice2-family",
        store=InMemoryCallRecordStore(),
        mission=daily_check_mission(),
    )
    result = session.start()
    text = ""
    if result is not None and getattr(result, "proposal", None) is not None:
        text = result.proposal.speech or ""
    eng = session._engine
    assert eng is not None
    if not text:
        speak = eng.pop_speak_effect()
        if speak is None and eng.state.active_playout is not None:
            text = eng.state.active_playout.text
        elif speak is not None:
            text = speak.text
    assert text
    assert "чувствуете" in text.lower() or "здравств" in text.lower()
    assert eng.state.mission_preset == "daily_check"


def test_curated_mvp_household_and_refusal_behaviours() -> None:
    """Small curated behavioural set (behavior, not exact old strings)."""
    # household → one help follow-up
    eng = _engine(provider=_Slice2FakeProvider())
    eng.start()
    _deliver(eng)
    eng.on_user_turn(
        "h1",
        "Батареи опять почти не греют.",
        rich_turn=RichUserTurn(
            utterance_id="h1",
            raw_text="Батареи опять почти не греют.",
            dialogue_act="answer",
            control="none",
            answers_pending_question=False,
            needs_clarification=False,
            issue_mentions=(
                IssueMention(
                    mention_id="im1",
                    kind="other",
                    label="батареи опять почти не греют",
                    role="primary",
                    body_site=None,
                    temporal_scope="now",
                    status="active",
                    onset=None,
                    severity=None,
                    evidence=Evidence(start=0, end=28, quote="батареи опять почти не греют"),
                ),
            ),
        ),
    )
    q = _deliver(eng)
    assert "справляетесь" in q.lower() or "помощь" in q.lower()

    # user refusal of goal ≠ call stop
    mission = CallMission(
        mission_id="refuse-goal",
        goals=(
            GoalDefinition(
                goal_id="ate_today",
                prompt_hint="Сегодня удалось поесть?",
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
            ),
        ),
    )
    eng2 = _engine(mission=mission)
    eng2.start()
    _deliver(eng2)
    eng2.on_user_turn(
        "r1",
        "Не хочу про это говорить.",
        rich_turn=RichUserTurn(
            utterance_id="r1",
            raw_text="Не хочу про это говорить.",
            dialogue_act="answer",
            control="none",
            answers_pending_question=True,
            needs_clarification=False,
            goal_dispositions=(
                GoalDispositionCandidate(
                    goal_id="ate_today",
                    disposition="declined",
                    confidence=0.95,
                    evidence="Не хочу про это говорить",
                ),
            ),
        ),
    )
    assert eng2.state.goals["ate_today"].lifecycle == GoalLifecycle.DECLINED
    assert not eng2.state.call_closed
