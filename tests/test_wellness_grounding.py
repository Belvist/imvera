"""Wellness grounding end-to-end (reporter table, pilot path).

One coherent segment: answer → recorded state → justified next action.
- substantive general assessment without complaint → concern probe
- garbage / "не знаю" / other-person-only → slot stays OPEN (re-ask)
- positive → routine ladder; mixed subjects stay separated
"""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.mission import daily_check_mission
from packages.dialogue_engine.mission_seed import apply_mission_to_state
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture(autouse=True)
def _pilot_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")


def _run(text: str):
    r = ScenarioRunner(call_id="well", elder_display_name="Тест")
    apply_mission_to_state(r.state, daily_check_mission())
    r.run([CallStarted()])
    res = r.run([text])
    return r, [e.intent for e in res.speak_effects]


@pytest.mark.parametrize(
    "text",
    [
        "по состоянию мне более-менее",
        "мне так себе",
        "плохо",
        "ни шатко ни валко",
        "кое-как",
        "помаленьку",
    ],
)
def test_substantive_nonpositive_probes_concern(text: str) -> None:
    r, intents = _run(text)
    assert intents == ["probe_concern"]
    assert r.state.slots["wellness"] == SlotStatus.FILLED
    assert r.state.slot_records["wellness"].polarity in ("negative", "uncertain")


@pytest.mark.parametrize("text", ["абракадабра", "не знаю", "у мужа плохо"])
def test_nonsubstantive_keeps_slot_open(text: str) -> None:
    r, intents = _run(text)
    assert r.state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness" not in r.state.slot_records
    assert "background_nutrition" not in intents
    assert "background_medication" not in intents


def test_positive_allows_ladder() -> None:
    r, intents = _run("хорошо")
    assert intents == ["background_nutrition"]
    assert r.state.slot_records["wellness"].polarity == "positive"


def test_mixed_subjects_split() -> None:
    r, intents = _run("у мужа плохо, а у меня более-менее")
    assert intents == ["probe_concern"]
    rec = r.state.slot_records["wellness"]
    assert "муж" not in rec.value.lower()
    assert "мужа" not in rec.source_text.lower()


def _run_seq(turns: list[str]):
    from packages.dialogue_engine.events import CallStarted

    r = _fresh()
    r.run([CallStarted()])
    intents: list[str] = []
    for t in turns:
        res = r.run([t])
        intents.extend(e.intent for e in res.speak_effects)
    return r, intents


def _fresh():
    from packages.dialogue_engine.mission import daily_check_mission
    from packages.dialogue_engine.mission_seed import apply_mission_to_state
    from packages.dialogue_engine.scenario_runner import ScenarioRunner

    r = ScenarioRunner(call_id="well", elder_display_name="Тест")
    apply_mission_to_state(r.state, daily_check_mission())
    return r


def test_deterioration_after_positive_probes() -> None:
    r, intents = _run_seq(["Хорошо.", "Плохо мне."])
    assert intents[-1] == "probe_concern"
    assert r.state.slot_records["wellness"].polarity == "negative"
    assert "background_medication" not in intents[1:]
    assert not r.state.call_closed


def test_uncertain_after_positive_probes() -> None:
    r, intents = _run_seq(["Хорошо.", "Так себе."])
    assert intents[-1] == "probe_concern"
    assert not r.state.call_closed


def test_negative_at_summary_reopens_instead_of_goodbye() -> None:
    r, intents = _run_seq(
        ["Хорошо.", "Поела.", "Нет.", "Нормальное.", "Выспалась.",
         "Дома буду.", "Нет, мне плохо."]
    )
    assert intents[-1] == "probe_concern"
    assert not r.state.call_closed


def test_clean_decline_still_closes() -> None:
    r, intents = _run_seq(
        ["Хорошо.", "Поела.", "Нет.", "Нормальное.", "Выспалась.",
         "Дома буду.", "Нет, ничего."]
    )
    assert intents[-1] == "goodbye_final"
    assert r.state.call_closed


def test_other_person_after_positive_keeps_speaker_record() -> None:
    r, intents = _run_seq(["Хорошо.", "У мужа плохо."])
    rec = r.state.slot_records["wellness"]
    assert rec.polarity == "positive"
    assert "муж" not in rec.value.lower()


def test_film_eval_is_not_health() -> None:
    # Live catch: «мне плохо от фильма» must not probe or record.
    r, intents = _run("Мне плохо от того, что я посмотрел фильм.")
    assert intents == ["clarify_wellness"]
    assert r.state.slots["wellness"].value == "OPEN"
    assert "wellness" not in r.state.slot_records


@pytest.mark.parametrize(
    "text",
    ["Фильм плохой.", "Еда плохая."],
)
def test_object_rating_redirects_to_self(text: str) -> None:
    from packages.dialogue_engine.events import CallStarted

    r = _fresh()
    r.run([CallStarted()])
    res = r.run([text])
    intents = [e.intent for e in res.speak_effects]
    texts = [e.text or "" for e in res.speak_effects]
    assert intents == ["clarify_wellness"]
    assert "вы сами как себя чувствуете" in texts[0].lower()
    assert "wellness" not in r.state.slot_records


@pytest.mark.parametrize(
    "text",
    ["Мне плохо.", "Мне плохо от боли.", "Мне плохо от жары.", "Ноги плохие."],
)
def test_bodily_negative_stays_health(text: str) -> None:
    r, intents = _run(text)
    assert "background_nutrition" not in intents
    assert "background_medication" not in intents
    assert r.state.slots["wellness"].value == "FILLED"


def test_episode_confusion_never_fabricates_nor_hangs_up() -> None:
    r, intents = _run_seq(
        ["Голова болит.", "Белиберда.", "Трамвай.", "Тарабарщина."]
    )
    assert "partial_unresolved_close" not in intents
    assert "summary" in intents
    ep = next(iter(r.state.issue_episodes.values()))
    vals = " ".join(
        str(v)
        for k, v in ep.known_attributes.items()
        if not k.startswith("_")
    ).lower()
    for junk in ("белиберда", "трамвай", "тарабарщина"):
        assert junk not in vals


def test_find_out_ladder_tries_thrice_then_marks_unknown() -> None:
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.events import CallStarted

    r = _fresh()
    r.run([CallStarted()])
    texts: list[str] = []
    intents: list[str] = []
    for t in ["Абракадабра.", "Белиберда.", "Трамвай."]:
        res = r.run([t])
        intents.extend(e.intent for e in res.speak_effects)
        texts.extend(e.text or "" for e in res.speak_effects)
    assert intents == ["clarify_wellness", "clarify_wellness", "wellness_unknown"]
    assert texts[0] != texts[1]  # hint, then concrete options
    assert "хорошо, нормально или плохо" in texts[1].lower()
    # Handoff, not walk-away: recorded for family/Core, call continues.
    assert "запишу" in texts[2].lower()
    assert "partial_unresolved_close" not in intents
    assert not r.state.call_closed
    assert r.state.slots["wellness"] == SlotStatus.UNRESOLVED
    assert r.state.goals["wellness"].status == SlotStatus.UNRESOLVED
    assert r.state.goals["wellness"].lifecycle.value == "UNCLEAR"
    assert r.state.goals["wellness"].answer is None
    assert "wellness" not in r.state.slot_records
    assert r.state.observations["wellness_unknown"] == "Трамвай."


def test_find_out_ladder_recovers_on_answer() -> None:
    r, intents = _run_seq(["Абракадабра.", "Белиберда.", "Хорошо."])
    assert intents[-1] == "background_nutrition"
    assert not r.state.call_closed


def _runtime_engine():
    from packages.dialogue_engine.effects import SpeakEffect
    from packages.dialogue_engine.engine import DialogueEngine

    engine = DialogueEngine(call_id="bounded-uncertainty")
    for effect in engine.start():
        if isinstance(effect, SpeakEffect):
            engine.on_playout_started(effect.generation, effect.question_id)
            engine.on_playout_completed(effect.generation, effect.question_id)
    return engine


def _runtime_reply(engine, text: str):
    from packages.dialogue_engine.effects import SpeakEffect
    from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

    uid = f"u-{engine.state.revision}"
    slot = engine.answer_context_slot()
    parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
    turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
    effects = engine.on_user_turn(uid, text, rich_turn=turn)
    speaks = [effect for effect in effects if isinstance(effect, SpeakEffect)]
    for effect in speaks:
        engine.on_playout_started(effect.generation, effect.question_id)
        engine.on_playout_completed(effect.generation, effect.question_id)
    return turn, speaks


@pytest.mark.parametrize("text", ["Не знаю.", "Абракадабра."])
def test_runtime_exhausted_uncertainty_is_unknown_and_bounded(text: str) -> None:
    from packages.dialogue_engine.mission_result import build_mission_result
    from packages.dialogue_engine.state import BackgroundGoalCoverage, EngineState, GoalLifecycle

    engine = _runtime_engine()
    intents = []
    for attempt in range(3):
        turn, speaks = _runtime_reply(engine, text)
        assert not turn.goal_answers
        intents.extend(effect.intent for effect in speaks)
        if attempt < 2:
            assert engine.state.slots["wellness"] == SlotStatus.OPEN
            assert engine.answer_context_slot() == "wellness"
    state = engine.state
    assert intents == ["clarify_wellness", "clarify_wellness", "wellness_unknown"]
    assert state.slots["wellness"] == SlotStatus.UNRESOLVED
    assert state.goals["wellness"].status == SlotStatus.UNRESOLVED
    assert state.goals["wellness"].lifecycle == GoalLifecycle.UNCLEAR
    assert state.goals["wellness"].answer is None
    assert "wellness" not in state.slot_records
    assert state.background_goal_status["wellness"] == BackgroundGoalCoverage.SKIPPED
    assert state.observations["wellness_unknown"] == text
    assert not state.call_closed
    restored = EngineState.model_validate_json(state.model_dump_json())
    result = build_mission_result(restored)
    wellness = next(goal for goal in result.goals if goal.goal_id == "wellness")
    assert wellness.lifecycle == "UNCLEAR"
    assert wellness.value is None
    assert result.status == "PARTIAL"
    _, speaks = _runtime_reply(engine, text)
    assert [effect.intent for effect in speaks] == ["important_to_share"]
    assert engine.state.slots["wellness"] == SlotStatus.UNRESOLVED
    assert not engine.state.call_closed


@pytest.mark.parametrize("text", ["Хорошо.", "Мне плохо."])
def test_runtime_answer_after_unknown_is_still_recorded(text: str) -> None:
    engine = _runtime_engine()
    for _ in range(3):
        _runtime_reply(engine, "Не знаю.")
    _, speaks = _runtime_reply(engine, text)
    assert engine.state.slots["wellness"] == SlotStatus.FILLED
    assert engine.state.slot_records["wellness"].value == text
    assert speaks
    assert not engine.state.call_closed


def test_runtime_real_refusal_is_not_unknown() -> None:
    from packages.dialogue_engine.mission_result import build_call_outcomes

    engine = _runtime_engine()
    _runtime_reply(engine, "Не хочу разговаривать.")
    assert engine.state.call_closed
    assert "wellness_unknown" not in engine.state.observations
    assert build_call_outcomes(engine.state).call_outcome == "DECLINED"
