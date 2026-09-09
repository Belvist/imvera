"""CallActor post-STT admission integration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.semantic_kernel.kernel import interpret
from packages.voice_perception.echo_ref_gate import EchoVerdict
from packages.voice_perception.post_stt_gate import TurnAdmissionVerdict, evaluate_post_stt_turn
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks

pytestmark = pytest.mark.dialogue_engine


def _noop(*_a, **_k):
    return None


def _session_with_engine() -> CallSession:
    session = CallSession(
        call_id="post-stt",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    assert session._engine is not None
    session._engine.state, _ = reduce(session._engine.state, CallStarted())
    return session


def test_severity_answer_not_echo_discarded() -> None:
    session = _session_with_engine()
    engine = session._engine
    assert engine is not None
    engine.state.pending_episode_attribute = "severity"
    engine.state.active_episode_id = "ep-headache"

    actor = CallActor(
        call_id=session.state.call_id,
        family_id="audit-family",
        session=session,
        stt=SimpleNamespace(),
        tts=SimpleNamespace(),
        llm=SimpleNamespace(),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
    )
    bot = "Боль сильная или терпимая?"
    actor._delivered_phrases.append(bot)
    session.state.pending_question = bot

    user = "Боль терпимая"
    kernel = interpret(user, utterance_id="u-sev", engine_state=engine.state)
    ctx = actor._build_post_stt_context(
        user,
        kernel,
        answer_slot="severity",
        pending_episode_attribute="severity",
        merged_from_fragment=False,
    )
    decision = evaluate_post_stt_turn(ctx)
    assert decision.verdict == TurnAdmissionVerdict.ACCEPT
    assert not actor._is_assistant_echo(user)


def test_onset_overlap_answer_accepted() -> None:
    session = _session_with_engine()
    engine = session._engine
    assert engine is not None
    engine.state.pending_episode_attribute = "onset"

    actor = CallActor(
        call_id=session.state.call_id,
        family_id="audit-family",
        session=session,
        stt=SimpleNamespace(),
        tts=SimpleNamespace(),
        llm=SimpleNamespace(),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
    )
    bot = "Как давно тошнит?"
    actor._delivered_phrases.append(bot)
    user = "Уже давно тошнит"
    kernel = interpret(user, utterance_id="u-onset", engine_state=engine.state)
    ctx = actor._build_post_stt_context(
        user,
        kernel,
        answer_slot=None,
        pending_episode_attribute="onset",
        merged_from_fragment=False,
    )
    decision = evaluate_post_stt_turn(ctx)
    assert decision.verdict == TurnAdmissionVerdict.ACCEPT


def test_acoustic_echo_drops_exact_reproduction() -> None:
    session = _session_with_engine()
    actor = CallActor(
        call_id=session.state.call_id,
        family_id="audit-family",
        session=session,
        stt=SimpleNamespace(),
        tts=SimpleNamespace(),
        llm=SimpleNamespace(),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
    )
    bot = "Боль сильная или терпимая?"
    actor._delivered_phrases.append(bot)
    actor._forensic_segment_echo_max = 0.92
    actor._segment_acoustic_echo_verdict = str(EchoVerdict.ECHO)
    user = bot
    kernel = interpret(user, utterance_id="u-echo")
    ctx = actor._build_post_stt_context(
        user,
        kernel,
        answer_slot="severity",
        pending_episode_attribute="severity",
        merged_from_fragment=False,
    )
    decision = evaluate_post_stt_turn(ctx)
    assert decision.verdict == TurnAdmissionVerdict.DROP_ECHO


def test_fragment_hold_and_merge() -> None:
    session = _session_with_engine()
    actor = CallActor(
        call_id=session.state.call_id,
        family_id="audit-family",
        session=session,
        stt=SimpleNamespace(),
        tts=SimpleNamespace(),
        llm=SimpleNamespace(),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
    )
    actor._hold_pending_fragment("Но", "u-frag")
    merged, was_merged = actor._merge_pending_fragment("ещё сильно тошнит")
    assert was_merged
    assert merged == "Но ещё сильно тошнит"
