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


def test_flow_mood_answer_to_wellness_asks_important_to_share() -> None:
    """Live fs-c83012aa: mood-only answer must not jump to summary."""
    r = _runner()
    r.run([CallStarted(), "Настроение вроде бы тоже нормальное."])
    intents = _intents(r)
    assert "important_to_share" in intents
    assert "summary" not in intents
    _no_background_ladder_before(intents, "important_to_share")
    assert r.state.slots["mood"].name == "FILLED"
    assert r.state.important_to_share_asked is True


def test_flow_fs_f534c2e6_soft_no_closes_warm() -> None:
    """Live fs-f534c2e6: soft «да вроде бы нет…» must not ask «расскажите коротко»."""
    r = ScenarioRunner(call_id="fs-f534c2e6", elder_display_name="Даниил")
    r.run([CallStarted()])
    r.run(["Привет! Чувствую себя хорошо, настроение хорошее."])
    assert "important_to_share" in _intents(r)
    its = [e for e in r.effects if getattr(e, "intent", "") == "important_to_share"]
    assert its
    assert "добавить" in its[-1].text.lower()
    result = r.run(
        [
            "Да вроде бы нет, планов толком тоже нет никаких. Так вроде всё нормально."
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    texts = " ".join(e.text.lower() for e in result.speak_effects)
    assert "summary" in intents
    assert "расскажите" not in texts
    assert "коротко" not in texts
    summary = next(e for e in result.speak_effects if e.intent == "summary")
    assert "Даниил" in summary.text
    assert "до свидания" in summary.text.lower()
    assert "всего" in summary.text.lower()
    assert result.state.slots["plans"].name == "FILLED"


def test_flow_important_share_recorded_then_warm_close() -> None:
    r = ScenarioRunner(call_id="share-note", elder_display_name="Даниил")
    r.run([CallStarted(), "Хорошо.", "Болит колено с утра."])
    assert r.state.observations.get("important_to_share")
    assert "колено" in str(r.state.observations["important_to_share"]).lower()
    summary = [e for e in r.effects if getattr(e, "intent", "") == "summary"]
    assert summary
    assert "записала" in summary[-1].text.lower()
    assert "Даниил" in summary[-1].text


def test_flow_summary_mentions_next_call_when_scheduled() -> None:
    r = ScenarioRunner(call_id="sched", elder_display_name="Даниил")
    r.state.prior_call_context["next_call_spoken"] = (
        "Следующий разговор в пять, перезвоню вам по расписанию."
    )
    r.run([CallStarted(), "Хорошо.", "Нет."])
    summary = [e for e in r.effects if getattr(e, "intent", "") == "summary"]
    assert summary
    assert "пять" in summary[-1].text.lower()
    assert "Даниил" in summary[-1].text


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
