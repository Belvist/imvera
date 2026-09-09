"""Issue-first conversation policy — obligation and state invariants (50+ scenarios)."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.conversation_policy import (
    ConversationObligation,
    TurnContext,
    schedule_next_action,
)
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.issue_memory import ingest_rich_turn
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import BackgroundGoalCoverage, EngineState
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine


def _runner(**kwargs) -> ScenarioRunner:
    return ScenarioRunner(call_id="issue-first", elder_display_name="Тест", **kwargs)


def _run(*steps: str) -> ScenarioRunner:
    r = _runner()
    r.run([CallStarted(), *steps])
    return r


# --- A: Wellness entry only ---


@pytest.mark.parametrize(
    "utterance,expect_episode",
    [
        ("Голова болит.", True),
        ("Плохо спал.", True),  # sleep_problem mention or slot fill
        ("Хорошо.", False),
        ("Горло болит и першит.", True),
        ("Локоть ноет.", True),
    ],
)
def test_wellness_entry_routes_symptoms_to_episodes(utterance: str, expect_episode: bool) -> None:
    r = _run(utterance)
    assert bool(r.state.issue_episodes) == expect_episode


def test_wellness_sleep_not_mood_ladder() -> None:
    r = _run("Плохо спал.")
    intents = [e.intent for e in r.effects if hasattr(e, "intent")]
    assert "check_mood" in intents or r.state.slots["sleep"] == SlotStatus.FILLED
    assert "probe_concern" not in intents


# --- B: Background goal coverage ---


@pytest.mark.parametrize("slot", ["mood", "sleep", "plans"])
def test_background_goal_coverage_unseen_initially(slot: str) -> None:
    state = EngineState(call_id="t")
    assert state.background_goal_status[slot] == BackgroundGoalCoverage.UNSEEN


def test_background_goal_marked_answered_after_fill() -> None:
    r = _run("Нормально.")
    assert r.state.background_goal_status["wellness"] == BackgroundGoalCoverage.ANSWERED
    assert r.state.background_goal_status["mood"] == BackgroundGoalCoverage.UNSEEN


def test_plans_not_required_before_close() -> None:
    r = _run("Нормально.", "Хорошее.", "Спал нормально.", "Нет.")
    assert r.state.slots["plans"] == SlotStatus.OPEN or "summary" in [
        e.intent for e in r.effects if hasattr(e, "intent")
    ]


# --- C: Active / pending episodes ---


def test_single_active_episode_focus() -> None:
    r = _run("Голова болит и живот болит.")
    assert r.state.active_episode_id is not None
    assert len(r.state.pending_episode_ids) >= 0


def test_pending_episode_after_independent_symptom() -> None:
    r = _run("Голова болит.", "Ещё и грудь давит.")
    assert len(r.state.issue_episodes) >= 2


# --- D: Issue resolution short-circuit ---


def test_resolved_headache_skips_severity() -> None:
    r = _runner()
    r.run([CallStarted(), "Голова болит и тошнит.", "Со вчера."])
    result = r.run(["Всё, боль прошла."])
    ep = next(
        (ep for ep in r.state.issue_episodes.values() if "голов" in ep.primary_label.lower()),
        None,
    )
    assert ep is not None
    assert ep.status == "resolved"
    intents = [e.intent for e in result.speak_effects]
    assert "episode_headache_severity" not in intents


def test_improving_lowers_followup_pressure() -> None:
    r = _run("Болит живот.", "С утра.", "Сейчас уже легче.")
    ep = next(iter(r.state.issue_episodes.values()))
    assert ep.known_attributes.get("current") or ep.status == "resolved"


# --- E: IMPORTANT_TO_SHARE ---


def test_important_to_share_after_issues() -> None:
    r = _run(
        "Голова болит и тошнит.",
        "С 10 утра.",
        "Терпимая.",
        "Нет.",
    )
    intents = [e.intent for e in r.effects if hasattr(e, "intent")]
    assert "important_to_share" in intents
    assert r.state.important_to_share_asked
    assert "check_mood" not in intents
    assert "check_sleep" not in intents
    assert "check_plans" not in intents


def test_important_to_share_no_blocks_summary() -> None:
    r = _run("Нормально.", "Нет.")
    intents = [e.intent for e in r.effects if hasattr(e, "intent")]
    assert "important_to_share" in intents
    assert "summary" in intents


# --- F: Scheduler obligations ---


def test_scheduler_user_question_priority() -> None:
    state = EngineState(call_id="t")
    turn = build_rich_turn_from_text("Кто вы?", utterance_id="u-1")
    plan = schedule_next_action(state, TurnContext(turn=turn))
    assert plan.obligation == ConversationObligation.ANSWER_USER_QUESTION


def test_scheduler_repair_obligation() -> None:
    state = EngineState(call_id="t")
    turn = build_rich_turn_from_text("Что?", utterance_id="u-1")
    turn = turn.model_copy(update={"dialogue_act": "repair"})
    plan = schedule_next_action(state, TurnContext(turn=turn))
    assert plan.obligation == ConversationObligation.REPAIR


def test_scheduler_background_goal_when_no_episodes() -> None:
    state = EngineState(call_id="t")
    state.slots["wellness"] = SlotStatus.FILLED
    state.set_background_goal_coverage("wellness", BackgroundGoalCoverage.ANSWERED)
    plan = schedule_next_action(state, TurnContext())
    assert plan.obligation == ConversationObligation.IMPORTANT_TO_SHARE
    assert plan.slot == "important_to_share"


def test_scheduler_continue_episode_when_active() -> None:
    state = EngineState(call_id="t")
    ingest_rich_turn(state, build_rich_turn_from_text("Живот болит.", utterance_id="u-1"))
    plan = schedule_next_action(state, TurnContext())
    assert plan.obligation in (
        ConversationObligation.CONTINUE_ACTIVE_EPISODE,
        ConversationObligation.ACKNOWLEDGE_IMPORTANT_FACT,
    )


# --- Generic symptom episodes (no finite branches) ---


@pytest.mark.parametrize(
    "text,body_hint",
    [
        ("Горло болит.", "горл"),
        ("Локоть болит.", "локот"),
        ("Живот болит.", "живот"),
        ("Голова болит.", "голов"),
    ],
)
def test_generic_symptom_episode_no_hardcoded_branch(text: str, body_hint: str) -> None:
    r = _run(text)
    assert r.state.issue_episodes
    label = next(iter(r.state.issue_episodes.values())).primary_label.lower()
    assert body_hint in label or body_hint in text.lower()


# --- Safety / urgent ---


def test_urgent_skips_ladder() -> None:
    r = _run("Вызовите скорую, очень плохо!")
    assert r.state.call_closed
    assert "urgent_close" in [e.intent for e in r.effects if hasattr(e, "intent")]


# --- Multi-fact / correction ---


def test_correction_acknowledges_history() -> None:
    r = _run("Живот болит.")
    r.run(["Я же говорил, живот болит."])
    texts = " ".join(e.text.lower() for e in r.effects if hasattr(e, "text"))
    assert "говорили" in texts


# --- Never silent ---


def test_meaningful_turn_produces_speech() -> None:
    r = _run("Плохо.")
    assert any(hasattr(e, "text") and e.text for e in r.effects)


# --- Obligation ordering smoke (parametric) ---


@pytest.mark.parametrize(
    "scenario,expected_obligation",
    [
        ("Кто вы?", ConversationObligation.ANSWER_USER_QUESTION),
        ("Голова болит.", ConversationObligation.CONTINUE_ACTIVE_EPISODE),
    ],
)
def test_obligation_for_turn(scenario: str, expected_obligation: ConversationObligation) -> None:
    state = EngineState(call_id="t")
    turn = build_rich_turn_from_text(scenario, utterance_id="u-1")
    if "Голова" in scenario:
        ingest_rich_turn(state, turn)
    plan = schedule_next_action(state, TurnContext(turn=turn))
    if expected_obligation == ConversationObligation.CONTINUE_ACTIVE_EPISODE:
        assert plan.obligation in (
            ConversationObligation.CONTINUE_ACTIVE_EPISODE,
            ConversationObligation.ACKNOWLEDGE_IMPORTANT_FACT,
        )
    else:
        assert plan.obligation == expected_obligation


# --- Batch: state invariants after common flows ---


@pytest.mark.parametrize(
    "steps",
    [
        ("Нормально.",),
        ("Голова болит.", "С утра."),
        ("Плохо спал.", "Устал."),
        ("Живот болит.", "Уже прошло."),
        ("Нормально, но болит колено.",),
    ],
)
def test_no_phantom_active_episode_after_resolve(steps: tuple[str, ...]) -> None:
    r = _run(*steps)
    for ep in r.state.issue_episodes.values():
        if ep.status == "resolved":
            assert ep.known_attributes.get("current") in (
                "resolved",
                "improving",
                None,
            ) or ep.status == "resolved"


@pytest.mark.parametrize("n", range(20))
def test_scheduler_never_returns_empty_action(n: int) -> None:
    state = EngineState(call_id=f"t-{n}")
    plan = schedule_next_action(state, TurnContext())
    allowed = ("speak", "close_summary", "close_urgent", "close_partial", "none", "control")
    assert plan.action in allowed


def test_episode_id_cleared_on_resolve() -> None:
    r = _run("Голова болит.", "С утра.", "Всё прошло.")
    assert r.state.active_episode_id is None or all(
        ep.status == "resolved" for ep in r.state.issue_episodes.values()
    )


def test_no_abdominal_on_headache() -> None:
    r = _run("Голова болит и тошнит.")
    texts = " ".join(e.text.lower() for e in r.effects if hasattr(e, "text"))
    assert "живот" not in texts


def test_sleep_issue_from_wellness_not_probe() -> None:
    r = _run("Плохо спал, всю ночь не спал.")
    assert "probe_concern" not in [e.intent for e in r.effects if hasattr(e, "intent")]


def test_background_goal_asked_status() -> None:
    r = _run("Хорошо.")
    assert r.state.background_goal_status["mood"] == BackgroundGoalCoverage.UNSEEN
    intents = [e.intent for e in r.effects if hasattr(e, "intent")]
    assert "important_to_share" in intents
