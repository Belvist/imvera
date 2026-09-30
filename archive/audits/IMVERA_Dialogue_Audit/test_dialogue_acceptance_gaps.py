"""Acceptance probes for f71de9d. Intentionally fail where dialogue loses meaning.

Run from the repository root with its dependencies installed:
  python -m pytest /path/to/test_dialogue_acceptance_gaps.py -q
Or set IMVERA_AUDIT_REPO to the repository root.
Fixtures describe correct semantic output; they do NOT test actual MLX accuracy.
No production modules are replaced or modified by this file.
"""

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(os.environ.get("IMVERA_AUDIT_REPO", ".")).resolve()))

from packages.contracts.enums import AsrQuality, FsmState, SlotStatus  # noqa: E402
from packages.contracts.semantic import Evidence, FactCandidate, SemanticPayload  # noqa: E402
from packages.core.memory_store import InMemoryCallRecordStore  # noqa: E402
from packages.dialogue.context_builder import active_question_kind, build_turn_context  # noqa: E402
from packages.dialogue.planner import Planner  # noqa: E402
from packages.dialogue.semantic_bridge import semantic_to_user_interpretation  # noqa: E402
from packages.dialogue.session import CallSession  # noqa: E402


def evidence(text, quote=None):
    quote = quote or text
    start = text.index(quote)
    return Evidence(start=start, end=start + len(quote), quote=quote)


def payload(**changes):
    values = dict(
        dialogue_act="answer", control="none", consent_answer="not_applicable",
        answers_pending_question=False, needs_clarification=False,
    )
    values.update(changes)
    return SemanticPayload(**values)


def fact(text, field="wellness", *, subject="speaker", temporal_scope="now", quote=None):
    return FactCandidate(
        field=field, value=quote or text, subject=subject, temporal_scope=temporal_scope,
        negated=False, evidence=evidence(text, quote),
    )


def daily_session():
    session = CallSession(call_id="audit-dialogue", family_id="audit-family",
                          store=InMemoryCallRecordStore())
    session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.state.fsm_state = FsmState.DAILY_CHECK
    Planner.plan_vera_turn(session.state, 2, "audit-open")
    return session


def apply(session, text, semantic):
    interp = semantic_to_user_interpretation(
        text, semantic, active_question_kind=active_question_kind(session.state),
    )
    return session.handle_user_text(text, interp=interp)


def test_fact_and_question_in_same_utterance_preserve_fact():
    session = daily_session()
    text = "Чувствую себя хорошо. А зачем вы спрашиваете?"
    apply(session, text, payload(
        dialogue_act="question", user_question="А зачем вы спрашиваете?",
        facts=(fact(text, quote="Чувствую себя хорошо"),), answers_pending_question=True,
    ))
    assert session.state.slots["wellness"] == SlotStatus.FILLED


def test_past_wellness_does_not_answer_how_are_you_now():
    session = daily_session()
    text = "На прошлой неделе чувствовала себя хорошо"
    apply(session, text, payload(facts=(fact(text, temporal_scope="past"),)))
    assert session.state.slots["wellness"] == SlotStatus.OPEN


def test_unknown_person_is_not_committed_as_elder():
    session = daily_session()
    text = "Чувствует себя хорошо"
    apply(session, text, payload(facts=(fact(text, subject="unknown"),)))
    assert session.state.slots["wellness"] == SlotStatus.OPEN


def test_defer_during_daily_check_ends_without_another_check_question():
    session = daily_session()
    text = "Давайте позже, я занята"
    result = apply(session, text, payload(control="defer", control_evidence=evidence(text)))
    assert session.state.call_finalized, result.validated.speech


def test_no_to_can_talk_does_not_repeat_same_question():
    session = daily_session()
    session.state.fsm_state = FsmState.CHECK_CAN_TALK
    session.state.pending_slot = None
    session.state.pending_question = None
    session.state.mandatory_checks["can_talk"] = False
    result = apply(session, "Нет", payload(
        consent_answer="no", consent_evidence=evidence("Нет"), answers_pending_question=True,
    ))
    assert session.state.call_finalized, result.validated.speech


def test_yes_to_goodbye_confirmation_closes_voice_path():
    session = daily_session()
    text = "Закончим разговор"
    apply(session, text, payload(control="stop_call", control_evidence=evidence(text)))
    assert session.state.awaiting_goodbye_confirm
    result = apply(session, "Да", payload(
        consent_evidence=evidence("Да"), answers_pending_question=True,
    ))
    assert session.state.call_finalized, result.validated.speech


def test_question_without_delivery_evidence_is_not_complete():
    session = daily_session()
    ctx = build_turn_context(session.state, turn_id=2, utterance_id="u2", raw_text="Да")
    assert ctx.pending_question_delivery != "complete"


def test_old_fact_does_not_acquire_current_utterance_as_source():
    session = daily_session()
    text = "Чувствую себя хорошо"
    apply(session, text, payload(facts=(fact(text),), answers_pending_question=True))
    ctx = build_turn_context(session.state, turn_id=99, utterance_id="u99", raw_text="Алло")
    assert ctx.confirmed_facts[0].source_utterance_id != "u99"


def test_risk_question_context_does_not_reuse_pending_wellness_question():
    session = daily_session()
    session.state.fsm_state = FsmState.RED_SIGNAL
    session.state.risk_handling = True
    session.state.risk_source_quote = "Я упала"
    ctx = build_turn_context(session.state, turn_id=3, utterance_id="u3", raw_text="Да")
    assert ctx.active_question_kind == "risk"
    assert ctx.pending_question != "Расскажите, как вы себя чувствуете сейчас?"


def test_real_second_utterance_is_not_lost_on_state_version_change():
    from packages.voice_runtime.call_actor import CallActor, MediaCallbacks

    async def scenario():
        session = daily_session()
        first_seen, both_seen, release_second = asyncio.Event(), asyncio.Event(), asyncio.Event()
        texts = {b"first": "Чувствую себя хорошо", b"second": "Спала плохо"}

        async def stt(pcm, *args, **kwargs):
            return SimpleNamespace(text=texts[pcm], asr_quality=AsrQuality.GOOD)

        async def llm(ctx, **kwargs):
            if ctx.raw_text == texts[b"first"]:
                first_seen.set()
                await both_seen.wait()
                field = "wellness"
            else:
                both_seen.set()
                await release_second.wait()
                field = "sleep"
            return SimpleNamespace(payload=payload(facts=(fact(ctx.raw_text, field),)))

        async def noop(*args, **kwargs):
            pass

        actor = CallActor(
            call_id=session.state.call_id, family_id="audit-family", session=session,
            stt=SimpleNamespace(transcribe_final=stt), tts=SimpleNamespace(),
            llm=SimpleNamespace(interpret_turn=llm), media=MediaCallbacks(noop, noop, noop, noop),
        )
        actor._deliver_session_turn = noop  # Output is outside this input-order regression.
        first = asyncio.create_task(actor._handle_utterance(b"first", 1))
        await first_seen.wait()
        second = asyncio.create_task(actor._handle_utterance(b"second", 2))
        await first
        release_second.set()
        await second
        assert session.state.slots["wellness"] == SlotStatus.FILLED
        assert session.state.slots["sleep"] == SlotStatus.FILLED

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


# Passing controls prove that the fixtures use the intended semantic path.
def test_control_current_self_fact_fills_slot():
    session = daily_session()
    text = "Чувствую себя хорошо"
    apply(session, text, payload(facts=(fact(text),), answers_pending_question=True))
    assert session.state.slots["wellness"] == SlotStatus.FILLED


def test_control_other_person_does_not_fill_slot():
    session = daily_session()
    text = "Соседка чувствует себя хорошо"
    apply(session, text, payload(facts=(fact(text, subject="other"),)))
    assert session.state.slots["wellness"] == SlotStatus.OPEN


def test_control_backchannel_does_not_fill_slot():
    session = daily_session()
    apply(session, "Алло", payload(dialogue_act="backchannel"))
    assert session.state.slots["wellness"] == SlotStatus.OPEN
