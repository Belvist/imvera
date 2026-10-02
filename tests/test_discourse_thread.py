"""Discourse thread + spoken past + signature ring (live-speech slices).

Thread: update_discourse tracks the person's topic from verified
semantics; the scheduler follows it once with a follow-up built from
their own words instead of jumping back to the ladder.
Past out loud: a fresh recurrence of a past complaint is acknowledged
as returning. Signatures: one normalized ring drives the rephrase
picker (asked_history stays as the verbatim recall store).
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.conversation_policy import (
    TurnContext,
    schedule_next_action,
)
from packages.dialogue_engine.discourse import normalize_signature, update_discourse
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.issue_memory import ingest_rich_turn
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine


def _turn(text: str):
    return build_rich_turn_from_text(text, utterance_id="u-t")


def test_thread_set_from_untyped_story_with_hook() -> None:
    # «Внучка приезжала» yields no facts/mentions — the most human
    # content must still start a thread, quoted back verbatim.
    state = EngineState(call_id="t-thread")
    turn = _turn("Внучка приезжала, хорошо посидели.")
    assert not turn.goal_facts and not turn.issue_mentions
    ingest_rich_turn(state, turn)
    # atomic funnel writes discourse; emulate via direct call parity
    update_discourse(state, turn)
    assert state.current_thread_label == "рассказ"
    assert "внучка" in state.open_hook.lower()
    assert not state.open_hook_used


def test_thread_set_from_typed_plans_fact() -> None:
    state = EngineState(call_id="t-plans")
    turn = _turn("Дома посижу, никуда не пойду.")
    assert turn.goal_facts
    update_discourse(state, turn)
    assert state.current_thread_label == "планы"


def test_thread_ignores_garbage_and_other_person() -> None:
    state = EngineState(call_id="t-quiet")
    update_discourse(state, _turn("Ага."))
    assert state.current_thread_label == ""
    assert state.open_hook == ""
    update_discourse(state, _turn("Муж плохо спал."))
    # other-person fact must not become Vera's thread
    assert state.current_thread_label == ""


def test_thread_decays_after_three_empty_turns() -> None:
    state = EngineState(call_id="t-decay")
    state.current_thread_label = "планы"
    for _ in range(3):
        update_discourse(state, _turn("Ага."))
    assert state.current_thread_label == ""


def test_thread_invite_keeps_source_without_parroting_or_forced_questions() -> None:
    r = ScenarioRunner(call_id="thread-follow", elder_display_name="Тест")
    result = r.run([CallStarted(), "Внучка приезжала, хорошо посидели."])
    assert r.state.current_thread_label == "рассказ"
    assert r.state.thread_last_statement == "Внучка приезжала, хорошо посидели."
    assert r.state.thread_last_utterance_id == "u-1"
    last = result.speak_effects[-1]
    assert last.intent == "thread_invite"
    assert not last.marks_question and "?" not in last.text
    assert "внучка" not in last.text.lower()
    assert r.state.thread_listening_delivered
    continuation = r.run(["Чай пили, разговаривали."]).speak_effects[-1]
    assert continuation.intent == "thread_listening_ack"
    assert "внучка" not in continuation.text.lower()


def test_spoken_past_on_recurrence() -> None:
    state = EngineState(call_id="t-past")
    state.prior_call_context = {"past_episodes": "головная боль@голова:resolved"}
    turn = _turn("Голова болит.")
    assert turn.issue_mentions
    ingest_rich_turn(state, turn)
    plan = schedule_next_action(state, TurnContext(turn=turn, user_text=turn.raw_text))
    assert state.observations.get("past_episode_reopened") == "головная боль"
    assert plan.acknowledge and "прошлый раз" in plan.acknowledge.lower()


def test_spoken_past_keeps_improving_ack() -> None:
    state = EngineState(call_id="t-ease")
    state.prior_call_context = {"past_episodes": "головная боль@голова:open"}
    turn = _turn("Голова уже почти прошла.")
    ingest_rich_turn(state, turn)
    plan = schedule_next_action(state, TurnContext(turn=turn, user_text=turn.raw_text))
    if plan.acknowledge:
        assert "Снова" not in plan.acknowledge


def test_signature_ring_written_and_read() -> None:
    r = ScenarioRunner(call_id="sig-ring", elder_display_name="Тест")
    r.run([CallStarted(), "Ага."])
    assert len(r.state.asked_signatures) <= 8
    assert all(s == normalize_signature(s) for s in r.state.asked_signatures)
    # every recorded question has a signature twin
    assert len(r.state.asked_signatures) == len(r.state.asked_history)


def test_rephrase_avoids_last_ack() -> None:
    state = EngineState(call_id="t-ack")
    state.last_ack_signature = normalize_signature("Ага, поняла вас")
    # pool path exercised through delivered question plumbing is covered
    # by existing rephrase tests; here only the signature helper contract
    assert state.last_ack_signature == "ага, поняла вас"
    assert normalize_signature("  Поняла ВАС?! ") == "поняла вас"
