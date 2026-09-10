"""Conversation-level issue-first flows (ADR-015)."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine

_BACKGROUND_LADDER = ("check_mood", "check_sleep", "check_plans", "clarify_mood", "clarify_sleep", "clarify_plans")


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="flows", elder_display_name="Тест")


def _intents(r: ScenarioRunner) -> list[str]:
    return [e.intent for e in r.effects if hasattr(e, "intent")]


def _no_background_ladder_before(intents: list[str], marker: str) -> None:
    if marker not in intents:
        pytest.fail(f"marker intent {marker!r} not in {intents}")
    idx = intents.index(marker)
    prefix = intents[:idx]
    for bad in _BACKGROUND_LADDER:
        assert bad not in prefix, f"{bad} before {marker}: {prefix}"


def test_flow_c_all_good_to_important_to_share() -> None:
    r = _runner()
    r.run([CallStarted(), "Всё хорошо", "Нет"])
    intents = _intents(r)
    _no_background_ladder_before(intents, "important_to_share")
    assert "important_to_share" in intents
    assert "summary" in intents


def test_flow_free_speech_wellness_mood_no_silence() -> None:
    """Live fs-996c3fa1 regression: multi-clause OK must speak IMPORTANT_TO_SHARE."""
    r = _runner()
    r.run([CallStarted(), "Хорошо, настроение нормальное, всё хорошо."])
    intents = _intents(r)
    assert "important_to_share" in intents
    _no_background_ladder_before(intents, "important_to_share")
    assert r.state.slots["wellness"].name == "FILLED"
    # Mood may be covered from speech; must not re-ask mood ladder
    assert "check_mood" not in intents
    speaks = [e for e in r.effects if getattr(e, "intent", None) == "important_to_share"]
    assert speaks and speaks[0].text.strip()


def test_flow_crisis_wellness_from_first_words() -> None:
    r = _runner()
    r.run([CallStarted(), "Мне плохо, я умираю"])
    assert r.state.slots["wellness"].name == "FILLED"
    rec = r.state.slot_records.get("wellness")
    assert rec is not None
    assert rec.polarity == "negative" or "плох" in (rec.value or "").lower()
    intents = _intents(r)
    assert intents
    assert any(getattr(e, "text", "").strip() for e in r.effects if hasattr(e, "text"))


def test_flow_free_order_plans_without_ladder() -> None:
    r = _runner()
    r.run(
        [
            CallStarted(),
            "Привет, да всё хорошо, дела сегодня хорошо, планов нет",
            "Нет",
        ]
    )
    intents = _intents(r)
    assert "important_to_share" in intents
    _no_background_ladder_before(intents, "important_to_share")
    assert r.state.slots["wellness"].name == "FILLED"
    assert r.state.slots["plans"].name == "FILLED"
    assert "summary" in intents


def test_session_live_silence_validator_no_longer_blocks() -> None:
    """CallActor path: Validator must allow engine IMPORTANT_TO_SHARE after free OK."""
    from packages.contracts.enums import AsrQuality
    from packages.dialogue.interpretation import interpret_user_turn, to_turn_interpretation
    from packages.dialogue.session import CallSession
    from packages.dialogue_engine.semantic_kernel.kernel import (
        interpret as kernel_interpret,
        kernel_to_rich_turn,
    )

    session = CallSession(call_id="fs-996c3fa1", family_id="fam-test", elder_display_name="Даниил")
    opening = session.start()
    speak = opening.speak_effect
    assert speak is not None
    session._playout_meta[speak.generation_id] = (speak.generation, speak.question_id)
    session._playout_effect_meta[speak.generation_id] = speak.effect_id
    session._engine.on_playout_started(speak.generation, speak.question_id)
    session.mark_spoken_action(speak.generation_id)

    text = "Хорошо, настроение нормальное, всё хорошо."
    kr = kernel_interpret(
        text,
        utterance_id="u-2",
        engine_state=session._engine.state,
        answer_slot="wellness",
    )
    rich = kernel_to_rich_turn(kr, answer_slot="wellness", engine_state=session._engine.state)
    interp = interpret_user_turn(session.state, text)
    contract = to_turn_interpretation(
        session.state, 2, text, interp, state_version=session.state.state_version
    )
    result = session.handle_user_text(
        text,
        interp=interp,
        contract=contract,
        utterance_id="u-2",
        asr_quality=AsrQuality.GOOD,
        rich_turn=rich,
    )
    assert result.speak_effect is not None
    assert result.validated.allowed is True
    assert result.proposal.intent == "important_to_share"
    assert result.proposal.mandatory_remaining == []


def test_flow_a_headache_improving_to_important_to_share() -> None:
    r = _runner()
    r.run([CallStarted(), "Голова болит и тошнит", "С утра, но сейчас уже лучше"])
    intents = _intents(r)
    _no_background_ladder_before(intents, "important_to_share")
    assert "important_to_share" in intents


def test_flow_sleep_to_important_to_share_no_mood_plans() -> None:
    r = _runner()
    r.run([CallStarted(), "Плохо спал, проснулся в четыре"])
    intents = _intents(r)
    _no_background_ladder_before(intents, "important_to_share")
    assert "important_to_share" in intents


def test_flow_mixed_identity_knee_no_background_ladder() -> None:
    r = _runner()
    r.run(
        [
            CallStarted(),
            "Нормально.",
            "А вы кто?",
            "Колено ноет.",
            "Второй день",
            "Ничего",
        ]
    )
    intents = _intents(r)
    assert "answer_user_question" in intents
    assert any(i.startswith("episode_") for i in intents)
    assert not any(i in intents for i in _BACKGROUND_LADDER)


def test_compound_temporal_current_closes_both() -> None:
    r = _runner()
    r.run([CallStarted(), "Голова болит", "С утра, сейчас уже лучше"])
    ep = next(iter(r.state.issue_episodes.values()))
    assert ep.status == "resolved" or ep.known_attributes.get("current")


def test_compound_known_current_asks_only_temporal() -> None:
    from packages.dialogue_engine.state import EngineState, IssueEpisode
    from packages.dialogue_engine.semantic_kernel.information_gain import best_question_need

    ep = IssueEpisode(
        episode_id="ep-1",
        primary_label="головная боль",
        kind="symptom",
        known_attributes={"current": "ещё болит"},
    )
    state = EngineState(call_id="t")
    need = best_question_need(state, ep)
    assert need is not None
    assert need.attribute in ("duration", "onset")
    assert not need.is_compound


def test_compound_known_duration_no_temporal_reask() -> None:
    from packages.dialogue_engine.state import EngineState, IssueEpisode
    from packages.dialogue_engine.semantic_kernel.information_gain import best_question_need

    ep = IssueEpisode(
        episode_id="ep-1",
        primary_label="головная боль",
        kind="symptom",
        known_attributes={"duration": "с утра", "onset": "с утра"},
    )
    state = EngineState(call_id="t")
    need = best_question_need(state, ep)
    assert need is None or need.attribute not in ("duration", "onset")
