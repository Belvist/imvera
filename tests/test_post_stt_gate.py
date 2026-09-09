"""Post-STT turn admission gate — echo, fragment, semantic novelty."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.semantic_kernel.kernel import interpret
from packages.voice_perception.echo_ref_gate import EchoVerdict
from packages.voice_perception.post_stt_gate import (
    PostSTTContext,
    TurnAdmissionVerdict,
    analyze_semantic_novelty,
    evaluate_post_stt_turn,
    is_incomplete_fragment,
)
from packages.voice_perception.text_echo import compute_text_similarity, is_text_echo_of_bot


def _ctx(
    user: str,
    bot: str,
    *,
    pending_attr: str | None = None,
    acoustic_verdict: str | None = None,
    acoustic_score: float = 0.0,
    playback_active: bool = False,
    echo_tail: bool = False,
    ms_since: int | None = 2000,
    merged: bool = False,
) -> PostSTTContext:
    kernel = interpret(user, utterance_id="u-test")
    return PostSTTContext(
        user_text=user,
        last_bot_text=bot,
        bot_candidates=(bot,),
        playback_active=playback_active,
        milliseconds_since_playout_end=ms_since,
        echo_tail_active=echo_tail,
        acoustic_echo_score=acoustic_score,
        acoustic_echo_verdict=acoustic_verdict,
        pending_episode_attribute=pending_attr,
        semantic_result=kernel,
        merged_from_fragment=merged,
    )


@pytest.mark.parametrize(
    ("bot", "user", "pending"),
    [
        ("Как давно тошнит?", "Уже давно тошнит.", "onset"),
        ("Как давно болит колено?", "Колено болит три дня.", "duration"),
        ("Сильно болит спина?", "Спина болит терпимо.", "severity"),
    ],
)
def test_answer_repeating_question_noun_is_accepted(
    bot: str, user: str, pending: str
) -> None:
    decision = evaluate_post_stt_turn(_ctx(user, bot, pending_attr=pending))
    assert decision.verdict == TurnAdmissionVerdict.ACCEPT


def test_severity_answer_accepted_not_phantom_echo() -> None:
    bot = "Боль сильная или терпимая?"
    user = "Боль терпимая."
    decision = evaluate_post_stt_turn(
        _ctx(user, bot, pending_attr="severity"),
    )
    assert decision.verdict == TurnAdmissionVerdict.ACCEPT
    metrics = compute_text_similarity(user, bot)
    assert float(metrics["user_coverage"]) >= 0.5
    assert not is_text_echo_of_bot(user, bot)


def test_duration_short_answer_accepted() -> None:
    bot = "Как давно болит голова?"
    user = "Четыре часа."
    decision = evaluate_post_stt_turn(
        _ctx(user, bot, pending_attr="duration"),
    )
    assert decision.verdict == TurnAdmissionVerdict.ACCEPT


def test_actual_echo_dropped_with_acoustic() -> None:
    bot = "Боль сильная или терпимая?"
    user = "Боль сильная или терпимая"
    decision = evaluate_post_stt_turn(
        _ctx(
            user,
            bot,
            acoustic_verdict=str(EchoVerdict.ECHO),
            acoustic_score=0.92,
            playback_active=True,
            ms_since=100,
            echo_tail=True,
        ),
    )
    assert decision.verdict == TurnAdmissionVerdict.DROP_ECHO


def test_high_overlap_without_acoustic_is_accepted() -> None:
    bot = "Боль сильная или терпимая?"
    user = "Боль сильная или терпимая"
    decision = evaluate_post_stt_turn(_ctx(user, bot))
    assert decision.verdict == TurnAdmissionVerdict.ACCEPT


def test_fragment_hold_but() -> None:
    kernel = interpret("Но", utterance_id="u-frag")
    novelty = analyze_semantic_novelty(
        kernel, answer_slot=None, pending_episode_attribute="severity"
    )
    assert is_incomplete_fragment("Но", novelty)
    decision = evaluate_post_stt_turn(
        _ctx("Но", "Боль сильная или терпимая?", pending_attr="severity"),
    )
    assert decision.verdict == TurnAdmissionVerdict.HOLD_FRAGMENT


def test_fragment_merge_accepted() -> None:
    bot = "Боль сильная или терпимая?"
    user = "Но ещё сильно тошнит"
    decision = evaluate_post_stt_turn(
        _ctx(user, bot, pending_attr="severity", merged=True),
    )
    assert decision.verdict == TurnAdmissionVerdict.ACCEPT


@pytest.mark.parametrize(
    "answer",
    [
        "да",
        "нет",
        "сильно",
        "три часа",
        "со вчера",
        "не знаю",
        "стоп",
        "терпимая",
    ],
)
def test_valid_short_answers_never_held(answer: str) -> None:
    bot = "Боль сильная или терпимая?"
    decision = evaluate_post_stt_turn(
        _ctx(answer, bot, pending_attr="severity"),
    )
    assert decision.verdict != TurnAdmissionVerdict.HOLD_FRAGMENT
    assert decision.verdict != TurnAdmissionVerdict.DROP_ECHO


def test_conversation_complaint_accepted() -> None:
    user = "Почему вы так долго отвечаете?"
    decision = evaluate_post_stt_turn(_ctx(user, "Как давно тошнит?"))
    assert decision.verdict == TurnAdmissionVerdict.ACCEPT
