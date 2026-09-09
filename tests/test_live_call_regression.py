"""Live-call regressions replayed offline (fs-77afbbf1, fs-78aadac2)."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.semantic_kernel.kernel import interpret
from packages.voice_perception.echo_ref_gate import EchoVerdict
from packages.voice_perception.post_stt_gate import (
    PostSTTContext,
    TurnAdmissionVerdict,
    evaluate_post_stt_turn,
)

pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="live-regression", elder_display_name="Даниил")


def test_fs_77afbbf1_headache_flow_no_duplicate_onset_no_echo_drop() -> None:
    """Replay fs-77afbbf1: duration answer must not re-ask onset; overlap answer accepted."""
    runner = _runner()
    result = runner.run(
        [
            CallStarted(),
            "Привет, чувствую себя не очень. Голова болит, чё-то плохо чувствую себя.",
            "Достаточно давно.",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    assert "episode_headache_onset" not in intents
    assert "episode_headache_severity" in intents
    ep = next(iter(result.state.issue_episodes.values()))
    assert ep.known_attributes.get("duration")

    bot = "Как давно болит голова?"
    user = "Голова болит уже давно."
    kernel = interpret(user, utterance_id="u-3", engine_state=result.state)
    decision = evaluate_post_stt_turn(
        PostSTTContext(
            user_text=user,
            last_bot_text=bot,
            bot_candidates=(bot,),
            pending_episode_attribute=result.state.pending_episode_attribute,
            semantic_result=kernel,
        )
    )
    assert decision.verdict == TurnAdmissionVerdict.ACCEPT

    follow = runner.run(["Голова болит уже давно."])
    assert follow.speak_effects
    assert not follow.partial_close


def test_fs_77afbbf1_actual_echo_still_drops_with_acoustic() -> None:
    bot = "Как давно болит голова?"
    user = "Как давно болит голова"
    kernel = interpret(user, utterance_id="u-echo")
    decision = evaluate_post_stt_turn(
        PostSTTContext(
            user_text=user,
            last_bot_text=bot,
            bot_candidates=(bot,),
            acoustic_echo_verdict=str(EchoVerdict.ECHO),
            acoustic_echo_score=0.92,
            playback_active=True,
            semantic_result=kernel,
        )
    )
    assert decision.verdict == TurnAdmissionVerdict.DROP_ECHO


def test_fs_78aadac2_garbled_wellness_then_smotri_does_not_hangup() -> None:
    """Replay fs-78aadac2: STT garbage + «Смотри.» must not partial_unresolved_close."""
    result = _runner().run([CallStarted(), "Четыреста", "Смотри."])
    intents = [e.intent for e in result.speak_effects]
    assert "partial_unresolved_close" not in intents
    assert not result.partial_close
    assert any(i in intents for i in ("repair_repeat", "clarify_wellness", "check_mood"))
