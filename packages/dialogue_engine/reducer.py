"""Single-writer reducer — synchronous, deterministic, no I/O."""

from __future__ import annotations

import uuid

from packages.contracts.enums import FsmState, SlotStatus
from packages.dialogue_engine import questions
from packages.dialogue_engine.check_path import (
    ProbeAction,
    advance_probe_phase,
    apply_wellness_branch,
    classify_wellness_path,
)
from packages.dialogue_engine.conversation_policy import (
    ConversationObligation,
    decide_conversation_policy,
    resume_episode_obligation,
)
from packages.dialogue_engine.effects import (
    Effect,
    EndCallEffect,
    InterpretEffect,
    SpeakEffect,
    TimerEffect,
)
from packages.dialogue_engine.events import (
    CallStarted,
    DeliveryDeferred,
    DialogueEvent,
    EffectFailed,
    InterpretationCompleted,
    PlayoutCancelled,
    PlayoutCompleted,
    PlayoutStarted,
    SpeakEffectStale,
    TimerExpired,
    UserTurnReceived,
)
from packages.dialogue_engine.policy import (
    apply_slot_answer,
    can_ask_slot,
    fill_from_semantic,
    mark_question_delivered,
    may_close_partial,
    release_reservation,
    reserve_question,
)
from packages.dialogue_engine.response_plan import build_response_plan, compose_speech
from packages.dialogue_engine.semantic import SemanticAct
from packages.dialogue_engine.semantic_kernel.observation_memory import atomic_semantic_apply
from packages.dialogue_engine.state import (
    CheckPath,
    EngineState,
    OpeningState,
    Question,
    QuestionPhase,
)
from packages.dialogue_engine.topic_tracker import (
    TopicPrompt,
    _topic_complete,
    is_topic_slot,
    next_topic_prompt,
    observe_topic_answer,
    prime_topics,
    should_start_topic_flow,
    topic_ack_for_family,
    topic_slot,
)
from packages.dialogue_engine.turn_understanding import RichUserTurn

_STANDARD_CHECK_SLOTS = frozenset({"wellness", "mood", "sleep", "plans"})

_CONTROL_HANGUP_INTENTS = frozenset(
    {
        "goodbye_final",
        "partial_unresolved_close",
        "urgent_close",
        "wrong_person_final",
        "defer_final",
        "revoke_consent_final",
    }
)

_STALE = "STALE_EFFECT_IGNORED"


def reduce(
    state: EngineState,
    event: DialogueEvent,
) -> tuple[EngineState, list[Effect]]:
    if isinstance(event, CallStarted):
        return _on_call_started(state)
    if isinstance(event, UserTurnReceived):
        return _on_user_turn(state, event)
    if isinstance(event, InterpretationCompleted):
        return _on_interpretation_completed(state, event)
    if isinstance(event, PlayoutStarted):
        return _on_playout_started(state, event)
    if isinstance(event, PlayoutCompleted):
        return _on_playout_completed(state, event)
    if isinstance(event, PlayoutCancelled):
        return _on_playout_cancelled(state, event)
    if isinstance(event, TimerExpired):
        return _on_timer_expired(state, event)
    if isinstance(event, DeliveryDeferred):
        return _on_delivery_deferred(state, event)
    if isinstance(event, SpeakEffectStale):
        return _on_speak_effect_stale(state, event)
    if isinstance(event, EffectFailed):
        return _on_effect_failed(state, event)
    return state, []


def _tag_effects(effects: list[Effect], state: EngineState) -> list[Effect]:
    tagged: list[Effect] = []
    for eff in effects:
        if hasattr(eff, "model_copy"):
            tagged.append(
                eff.model_copy(
                    update={
                        "revision": state.revision,
                        "effect_id": eff.effect_id or _new_effect_id(),
                    }
                )
            )
        else:
            tagged.append(eff)
    return tagged


def _new_effect_id() -> str:
    return f"fx-{uuid.uuid4().hex[:8]}"


def _stale(state: EngineState, event_revision: int) -> bool:
    return event_revision > 0 and event_revision != state.revision


def _on_call_started(state: EngineState) -> tuple[EngineState, list[Effect]]:
    if state.opening_state != OpeningState.NOT_STARTED:
        return state, []
    if state.first_user_turn_received:
        return state, []
    state.fsm_state = FsmState.DAILY_CHECK
    state.opening_state = OpeningState.PLAYING
    state.opening_play_count += 1
    return _emit_speak(
        state,
        text=questions.opening_speech(
            state.elder_display_name,
            state.prior_call_context or None,
        ),
        intent="opening_wellness",
        slot="wellness",
        marks_question=True,
    )


def _emit_speak(
    state: EngineState,
    *,
    text: str,
    intent: str,
    slot: str | None,
    marks_question: bool,
) -> tuple[EngineState, list[Effect]]:
    gen_id = state.next_generation_id()
    gen = state.active_playout_generation + 1
    state.active_playout_generation = gen
    q = Question(
        question_id=gen_id,
        slot=slot or "",
        text=text,
        phase=QuestionPhase.PLANNED,
        intent=intent,
    )
    state.planned_question = q if marks_question else None
    state.playing_question = q if marks_question else None
    state.active_playout = q
    if marks_question and slot:
        if not reserve_question(state, slot, gen_id):
            return _close_partial(state)
    state.bump_revision()
    effect = SpeakEffect(
        effect_id=_new_effect_id(),
        revision=state.revision,
        generation_id=gen_id,
        generation=gen,
        text=text,
        intent=intent,
        question_id=gen_id if marks_question else "",
        slot=slot,
        marks_question=marks_question,
    )
    return state, [effect]


def _on_playout_started(
    state: EngineState,
    event: PlayoutStarted,
) -> tuple[EngineState, list[Effect]]:
    if _stale(state, event.revision):
        return state, []
    if event.generation != state.active_playout_generation:
        return state, []
    if state.playing_question and state.playing_question.question_id == event.question_id:
        state.playing_question = state.playing_question.model_copy(
            update={"phase": QuestionPhase.PLAYING}
        )
    state.bump_revision()
    return state, []


def _on_playout_completed(
    state: EngineState,
    event: PlayoutCompleted,
) -> tuple[EngineState, list[Effect]]:
    if _stale(state, event.revision):
        return state, []
    if event.generation != state.active_playout_generation:
        return state, []
    q = state.playing_question
    if q is not None:
        if event.question_id and q.question_id != event.question_id:
            return state, []
        delivered = q.model_copy(update={"phase": QuestionPhase.DELIVERED})
        state.delivered_question = delivered
        state.playing_question = None
        state.planned_question = None
        state.active_playout = None
        if q.intent == "opening_wellness":
            state.opening_state = OpeningState.DELIVERED
        if q.slot:
            mark_question_delivered(state, q.slot, q.question_id)
        state.bump_revision()
        if (
            q.slot
            and state.fsm_state == FsmState.DAILY_CHECK
            and not state.call_closed
        ):
            state.waiting_on_slot = q.slot
            return state, [
                TimerEffect(
                    effect_id=_new_effect_id(),
                    revision=state.revision,
                    timer_id=f"wait-{q.slot}",
                    wait_ms=questions._ANSWER_WAIT_MS,
                    reason="answer_wait",
                )
            ]
        return state, []

    ap = state.active_playout
    if ap is None:
        return state, []
    if event.question_id and ap.question_id and ap.question_id != event.question_id:
        return state, []
    state.active_playout = None
    state.bump_revision()
    if ap.intent in _CONTROL_HANGUP_INTENTS:
        return state, [
            EndCallEffect(
                effect_id=_new_effect_id(),
                revision=state.revision,
                reason=state.closing_reason or ap.intent,
            )
        ]
    return state, []


def _on_playout_cancelled(
    state: EngineState,
    event: PlayoutCancelled,
) -> tuple[EngineState, list[Effect]]:
    if _stale(state, event.revision):
        return state, []
    if event.generation != state.active_playout_generation:
        return state, []
    if state.playing_question:
        release_reservation(state, state.playing_question.slot)
        state.playing_question = state.playing_question.model_copy(
            update={"phase": QuestionPhase.CANCELLED}
        )
        state.playing_question = None
        state.planned_question = None
    if state.active_playout:
        state.active_playout = None
    state.bump_revision()
    return state, []


def _on_user_turn(
    state: EngineState,
    event: UserTurnReceived,
) -> tuple[EngineState, list[Effect]]:
    if state.call_closed:
        return state, []
    if _stale(state, event.revision):
        return state, []
    state.first_user_turn_received = True
    state.turn_seq += 1
    if event.effect_id and event.semantic is None and event.rich_turn is None:
        state.processing_turn_id = event.turn_id
        state.processing_effect_id = event.effect_id
        state.bump_revision()
        return state, [
            InterpretEffect(
                effect_id=event.effect_id,
                revision=state.revision,
                turn_id=event.turn_id,
                text=event.text,
            )
        ]
    if event.rich_turn is not None:
        state.processing_turn_id = event.turn_id
        state.processing_effect_id = event.effect_id or None
        return _apply_rich_turn(state, event.rich_turn)
    if event.semantic is None:
        return state, []
    state.processing_turn_id = event.turn_id
    state.processing_effect_id = event.effect_id or None
    return _apply_semantic(state, event.semantic)


def _on_interpretation_completed(
    state: EngineState,
    event: InterpretationCompleted,
) -> tuple[EngineState, list[Effect]]:
    if state.call_closed:
        return state, []
    if event.turn_id != state.processing_turn_id:
        return state, []
    if state.processing_effect_id and event.effect_id != state.processing_effect_id:
        return state, []
    if _stale(state, event.revision):
        return state, []
    return _apply_semantic(state, event.semantic)


def _apply_goal_facts(state: EngineState, turn: RichUserTurn) -> list[str]:
    filled: list[str] = []
    for fact in turn.goal_facts:
        if state.slots.get(fact.field) != SlotStatus.OPEN:
            continue
        apply_slot_answer(
            state,
            fact.field,
            fact.value,
            turn_id=turn.utterance_id,
            polarity="negative" if fact.value == "negative" else "positive",
            confidence=0.9,
            correction=turn.correction,
        )
        if fact.evidence and fact.evidence.quote:
            rec = state.slot_records.get(fact.field)
            if rec is not None:
                state.slot_records[fact.field] = rec.model_copy(
                    update={"source_text": fact.evidence.quote}
                )
        filled.append(fact.field)
    return filled


def _apply_rich_turn(
    state: EngineState,
    turn: RichUserTurn,
) -> tuple[EngineState, list[Effect]]:
    user_text = turn.raw_text
    answer_slot = state.answer_context_slot()

    if turn.answers_pending_question and state.pending_episode_attribute:
        state.delivered_question = None
        state.planned_question = None

    if state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE) or state.awaiting_goodbye_confirm:
        semantic_bridge = _rich_to_semantic(turn)
        closing = _handle_closing_turn(state, semantic_bridge)
        if closing is not None:
            state.processing_turn_id = None
            state.processing_effect_id = None
            return closing

    control_outcome = _apply_rich_control(state, turn)
    if control_outcome is not None:
        return control_outcome

    if turn.dialogue_act == "backchannel":
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.bump_revision()
        if (
            state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE)
            and not state.awaiting_goodbye_confirm
        ):
            return state, []
        if answer_slot:
            state.waiting_on_slot = answer_slot
            return state, [
                TimerEffect(
                    effect_id=_new_effect_id(),
                    revision=state.revision,
                    timer_id=f"wait-{answer_slot}",
                    wait_ms=7000,
                    reason="backchannel",
                )
            ]
        if _is_meaningful_turn(user_text):
            return _speak_never_silent(state, answer_slot or "wellness", user_text)
        return state, []

    if is_topic_slot(answer_slot):
        from packages.dialogue_engine.topic_tracker import (
            observe_topic_answer,
            sync_topic_hints_from_answer,
        )

        sync_topic_hints_from_answer(state, user_text, answer_slot=answer_slot)
        atomic_semantic_apply(state, turn)
        if turn.user_question and not turn.answers_pending_question:
            decision = decide_conversation_policy(state, turn)
            if decision is not None and decision.text:
                if decision.suspend is not None:
                    state.suspended_obligation = decision.suspend
                state.processing_turn_id = None
                state.processing_effect_id = None
                state.bump_revision()
                return _emit_speak(
                    state,
                    text=decision.text,
                    intent=decision.intent or "rich_policy",
                    slot=decision.slot or answer_slot or "wellness",
                    marks_question=decision.marks_question,
                )
        if turn.correction:
            decision = decide_conversation_policy(state, turn)
            if decision is not None and decision.text:
                state.processing_turn_id = None
                state.processing_effect_id = None
                state.bump_revision()
                return _emit_speak(
                    state,
                    text=decision.text,
                    intent=decision.intent or "rich_policy",
                    slot=decision.slot or answer_slot or "wellness",
                    marks_question=decision.marks_question,
                )
        newly_filled = _apply_goal_facts(state, turn)
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        state.bump_revision()
        observe_topic_answer(state, user_text)
        return _advance_after_topic(state, user_text, newly_filled=newly_filled)

    if state.probe_phase and turn.dialogue_act == "answer":
        if should_start_topic_flow(
            state, user_text, answer_slot=f"probe_{state.probe_phase}"
        ):
            atomic_semantic_apply(state, turn)
            state.probe_phase = None
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            state.bump_revision()
            prime_topics(state, user_text)
            return _advance_after_topic(state, user_text, newly_filled=[])
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        state.bump_revision()
        return _advance_probe_after_answer(state, user_text)

    atomic_semantic_apply(state, turn)

    if turn.user_question and not turn.answers_pending_question:
        decision = decide_conversation_policy(state, turn)
        if decision is not None and decision.text:
            if decision.suspend is not None:
                state.suspended_obligation = decision.suspend
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.bump_revision()
            return _emit_speak(
                state,
                text=decision.text,
                intent=decision.intent or "rich_policy",
                slot=decision.slot or answer_slot or "wellness",
                marks_question=decision.marks_question,
            )

    if turn.needs_clarification:
        from packages.dialogue_engine.semantic_kernel.kernel import clarify_text
        from packages.dialogue_engine.semantic_kernel.types import SemanticKernelResult

        stub = SemanticKernelResult(
            raw_text=user_text,
            utterance_id=turn.utterance_id,
            ambiguity=turn.kernel_ambiguities,
            level=turn.kernel_level,
        )
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.bump_revision()
        return _emit_speak(
            state,
            text=clarify_text(stub),
            intent="semantic_clarify",
            slot=answer_slot or "wellness",
            marks_question=True,
        )

    if turn.correction:
        decision = decide_conversation_policy(state, turn)
        if decision is not None and decision.text:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.bump_revision()
            return _emit_speak(
                state,
                text=decision.text,
                intent=decision.intent or "rich_policy",
                slot=decision.slot or answer_slot or "wellness",
                marks_question=decision.marks_question,
            )

    newly_filled = _apply_goal_facts(state, turn)
    if newly_filled:
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        state.bump_revision()
        return _advance_after_fills(state, newly_filled)

    decision = decide_conversation_policy(state, turn)
    if decision is not None:
        if decision.obligation == ConversationObligation.CONTROL and decision.control:
            control_outcome = _apply_rich_control(state, turn)
            if control_outcome is not None:
                return control_outcome
        if decision.text:
            if decision.suspend is not None:
                state.suspended_obligation = decision.suspend
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.bump_revision()
            return _emit_speak(
                state,
                text=decision.text,
                intent=decision.intent or "rich_policy",
                slot=decision.slot or answer_slot or "wellness",
                marks_question=decision.marks_question,
            )

    if any(m.kind == "sleep_problem" for m in turn.issue_mentions):
        if should_start_topic_flow(state, user_text, answer_slot=answer_slot):
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            state.probe_phase = None
            prime_topics(state, user_text)
            return _advance_after_topic(state, user_text, newly_filled=[])

    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    if state.active_episode_id or state.pending_episode_ids:
        resumed = decide_conversation_policy(state, turn)
        if resumed and resumed.text:
            return _emit_speak(
                state,
                text=resumed.text,
                intent=resumed.intent,
                slot=resumed.slot or "wellness",
                marks_question=resumed.marks_question,
            )
    if _is_meaningful_turn(user_text) and answer_slot:
        return _speak_never_silent(state, answer_slot, user_text)
    return state, []


def _rich_to_semantic(turn: RichUserTurn):
    from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn

    if turn.control == "stop_call":
        return SemanticTurn(
            act=SemanticAct.GOODBYE_REQUEST,
            source_quote=turn.raw_text,
            confidence=0.95,
        )
    if turn.dialogue_act == "backchannel":
        return SemanticTurn(act=SemanticAct.BACKCHANNEL, source_quote=turn.raw_text)
    if turn.dialogue_act == "correction":
        return SemanticTurn(
            act=SemanticAct.ANSWER,
            correction=True,
            source_quote=turn.raw_text,
            value=turn.raw_text,
        )
    return SemanticTurn(
        act=SemanticAct.ANSWER,
        source_quote=turn.raw_text,
        value=turn.raw_text,
        confidence=0.85,
    )


def _apply_rich_control(
    state: EngineState,
    turn: RichUserTurn,
) -> tuple[EngineState, list[Effect]] | None:
    control = turn.control
    if control in ("none", ""):
        return None

    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()

    if control == "stop_call":
        closing = _handle_closing_turn(state, _rich_to_semantic(turn))
        if closing is not None:
            return closing

    if control == "wrong_person":
        state.call_closed = True
        state.closing_reason = "wrong_person"
        state.fsm_state = FsmState.FINAL_CLASSIFICATION
        return _emit_speak(
            state,
            text=questions._WRONG_PERSON_FINAL,
            intent="wrong_person_final",
            slot=None,
            marks_question=False,
        )

    if control in ("defer", "revoke_consent"):
        state.call_closed = True
        state.closing_reason = control
        state.fsm_state = FsmState.FINAL_CLASSIFICATION
        text = (
            questions._REVOKE_FINAL
            if control == "revoke_consent"
            else questions._DEFER_FINAL
        )
        intent = "revoke_consent_final" if control == "revoke_consent" else "defer_final"
        return _emit_speak(
            state,
            text=text,
            intent=intent,
            slot=None,
            marks_question=False,
        )

    if control == "pause":
        slot = state.answer_context_slot() or "wellness"
        state.waiting_on_slot = slot
        state, effects = _emit_speak(
            state,
            text=questions._PAUSE_ACK,
            intent="pause_ack",
            slot=slot,
            marks_question=False,
        )
        effects.append(
            TimerEffect(
                effect_id=_new_effect_id(),
                revision=state.revision,
                timer_id=f"wait-{slot}",
                wait_ms=7000,
                reason="pause",
            )
        )
        return state, effects

    return None


def _apply_semantic(
    state: EngineState,
    semantic,
) -> tuple[EngineState, list[Effect]]:
    if state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE) or state.awaiting_goodbye_confirm:
        closing = _handle_closing_turn(state, semantic)
        if closing is not None:
            state.processing_turn_id = None
            state.processing_effect_id = None
            return closing

    answer_slot = state.answer_context_slot()

    user_text = semantic.source_quote or semantic.value or ""

    if semantic.act == SemanticAct.REPAIR_REQUEST:
        if state.delivered_question is None:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.bump_revision()
            if answer_slot:
                return state, [
                    TimerEffect(
                        effect_id=_new_effect_id(),
                        revision=state.revision,
                        timer_id=f"wait-{answer_slot}",
                        wait_ms=7000,
                        reason="backchannel",
                    )
                ]
            if _is_meaningful_turn(user_text):
                return _speak_never_silent(state, answer_slot or "wellness", user_text)
            return state, []
        state.processing_turn_id = None
        state.processing_effect_id = None
        return _speak_repair(state, answer_slot or semantic.target_slot or "wellness")

    if semantic.act == SemanticAct.BACKCHANNEL:
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.bump_revision()
        if (
            state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE)
            and not state.awaiting_goodbye_confirm
        ):
            return state, []
        if answer_slot:
            state.waiting_on_slot = answer_slot
            return state, [
                TimerEffect(
                    effect_id=_new_effect_id(),
                    revision=state.revision,
                    timer_id=f"wait-{answer_slot}",
                    wait_ms=7000,
                    reason="backchannel",
                )
            ]
        if _is_meaningful_turn(user_text):
            return _speak_never_silent(state, answer_slot or "wellness", user_text)
        return state, []

    if semantic.act == SemanticAct.UNCLEAR and answer_slot:
        if is_topic_slot(answer_slot) and _is_meaningful_turn(user_text):
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            observe_topic_answer(state, user_text)
            return _advance_after_topic(state, user_text)
        if state.probe_phase:
            count = state.slot_unclear_counts.get(f"probe_{state.probe_phase}", 0) + 1
            state.slot_unclear_counts[f"probe_{state.probe_phase}"] = count
            state.processing_turn_id = None
            state.processing_effect_id = None
            if count >= 2:
                return _advance_probe_after_answer(state, user_text)
            return _speak_probe(state, state.probe_phase, clarification=True)
        count = state.slot_unclear_counts.get(answer_slot, 0) + 1
        state.slot_unclear_counts[answer_slot] = count
        state.processing_turn_id = None
        state.processing_effect_id = None
        if may_close_partial(state, answer_slot):
            return _close_partial(state)
        if can_ask_slot(state, answer_slot):
            return _speak_slot_question(state, answer_slot, clarification=True)
        if _is_meaningful_turn(user_text):
            return _speak_never_silent(state, answer_slot, user_text)
        return state, []

    if state.probe_phase and semantic.act == SemanticAct.ANSWER:
        text = semantic.value or semantic.source_quote
        if should_start_topic_flow(
            state, text, answer_slot=f"probe_{state.probe_phase}"
        ):
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            state.probe_phase = None
            prime_topics(state, text)
            return _advance_after_topic(state, text, newly_filled=[])
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        return _advance_probe_after_answer(state, text)

    if is_topic_slot(answer_slot) and semantic.act == SemanticAct.ANSWER:
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        observe_topic_answer(state, user_text)
        return _advance_after_topic(state, user_text)

    if (
        semantic.act == SemanticAct.ANSWER
        and semantic.slots
        and len(_STANDARD_CHECK_SLOTS.intersection(semantic.slots)) >= 2
    ):
        filled = fill_from_semantic(
            state, semantic, turn_id=state.processing_turn_id or ""
        )
        if filled:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            return _advance_after_fills(state, filled)

    if should_start_topic_flow(state, user_text, answer_slot=answer_slot):
        if semantic.act in (SemanticAct.ANSWER, SemanticAct.UNCLEAR):
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            state.probe_phase = None
            prime_topics(state, user_text)
            return _advance_after_topic(state, user_text, newly_filled=[])

    filled = fill_from_semantic(
        state, semantic, turn_id=state.processing_turn_id or ""
    )
    if filled:
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        return _advance_after_fills(state, filled)

    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    if _is_meaningful_turn(user_text) and answer_slot:
        return _speak_never_silent(state, answer_slot, user_text)
    return state, []


def _is_meaningful_turn(text: str) -> bool:
    core = text.strip()
    if len(core) < 2:
        return False
    if core.lower() in {"да", "нет", "ага", "угу"}:
        return True
    return len(core.split()) >= 1


def _speak_never_silent(
    state: EngineState,
    answer_slot: str,
    user_text: str,
) -> tuple[EngineState, list[Effect]]:
    """No substantive user turn may end with zero Vera response."""
    if is_topic_slot(answer_slot):
        observe_topic_answer(state, user_text)
        advanced = _advance_after_topic(state, user_text)
        if advanced[1]:
            return advanced
    if state.probe_phase:
        return _speak_probe(state, state.probe_phase, clarification=True)
    if can_ask_slot(state, answer_slot):
        ack = "Понимаю."
        question = questions.slot_question(answer_slot, clarification=True, state=state)
        return _emit_speak(
            state,
            text=f"{ack} {question}".strip(),
            intent=f"clarify_{answer_slot}",
            slot=answer_slot,
            marks_question=True,
        )
    if may_close_partial(state, answer_slot):
        return _close_partial(state)
    return _speak_repair(state, answer_slot)


def _advance_after_fills(
    state: EngineState,
    filled_slots: list[str],
) -> tuple[EngineState, list[Effect]]:
    state.delivered_question = None

    if "wellness" in filled_slots:
        rec = state.slot_records.get("wellness")
        wellness_text = (rec.source_text if rec else "") or state.slot_values.get("wellness", "")
        if should_start_topic_flow(state, wellness_text, answer_slot="wellness"):
            state.probe_phase = None
            prime_topics(state, wellness_text)
            return _advance_after_topic(state, wellness_text, newly_filled=filled_slots)
        branch = _branch_after_wellness(state)
        if branch is not None:
            return branch

    next_slot = state.next_open_slot()
    if next_slot is None:
        return _emit_summary(state)
    if not can_ask_slot(state, next_slot):
        return _close_partial(state)
    plan = build_response_plan(state, newly_filled=filled_slots, next_slot=next_slot)
    text = compose_speech(plan)
    intent = f"check_{next_slot}"
    return _emit_speak(
        state,
        text=text,
        intent=intent,
        slot=next_slot,
        marks_question=True,
    )


def _topics_need_attention(state: EngineState) -> bool:
    if state.active_topic and not _topic_complete(state, state.active_topic):
        return True
    return any(not _topic_complete(state, family) for family in state.pending_topics)


def _advance_after_topic(
    state: EngineState,
    user_text: str,
    *,
    newly_filled: list[str] | None = None,
) -> tuple[EngineState, list[Effect]]:
    state.delivered_question = None
    state.planned_question = None
    prompt = next_topic_prompt(state)
    if prompt is not None:
        return _emit_topic_prompt(state, prompt, newly_filled=newly_filled or [])
    state.active_topic = None
    state.topic_asked_dimension = None
    if not _topics_need_attention(state):
        episode_resume = resume_episode_obligation(state)
        if episode_resume is not None and episode_resume.text:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.bump_revision()
            return _emit_speak(
                state,
                text=episode_resume.text,
                intent=episode_resume.intent or "episode_resume",
                slot=episode_resume.slot,
                marks_question=episode_resume.marks_question,
            )
    next_slot = state.next_open_slot()
    if next_slot is None:
        return _emit_summary(state)
    if not can_ask_slot(state, next_slot):
        return _close_partial(state)
    ack = ""
    if newly_filled:
        ack = build_response_plan(
            state, newly_filled=newly_filled, next_slot=next_slot
        ).acknowledge
    plan = build_response_plan(state, newly_filled=[], next_slot=next_slot)
    parts = [p for p in (ack, plan.mandatory_question) if p]
    text = " ".join(parts)
    return _emit_speak(
        state,
        text=text,
        intent=f"check_{next_slot}",
        slot=next_slot,
        marks_question=True,
    )


def _emit_topic_prompt(
    state: EngineState,
    prompt: TopicPrompt,
    *,
    newly_filled: list[str],
) -> tuple[EngineState, list[Effect]]:
    ack_parts: list[str] = []
    if newly_filled:
        ack_parts.append(
            build_response_plan(
                state,
                newly_filled=newly_filled,
                next_slot=state.next_open_slot() or "mood",
            ).acknowledge
        )
    ack_parts.append(topic_ack_for_family(prompt.family))
    question = questions.topic_question(prompt.intent)
    text = " ".join(p for p in ack_parts if p).strip()
    if text and question:
        text = f"{text} {question}"
    elif question:
        text = question
    slot = topic_slot(prompt.family)
    return _emit_speak(
        state,
        text=text,
        intent=prompt.intent,
        slot=slot,
        marks_question=True,
    )


def _branch_after_wellness(state: EngineState) -> tuple[EngineState, list[Effect]] | None:
    if not state.wellness_probes_enabled:
        return None
    rec = state.slot_records.get("wellness")
    text = (rec.source_text if rec else "") or state.slot_values.get("wellness", "")
    polarity = rec.polarity if rec else None
    branch = classify_wellness_path(wellness_text=text, polarity=polarity)
    if branch.path == CheckPath.STANDARD:
        return None
    apply_wellness_branch(state, branch)
    if branch.urgent:
        return _emit_urgent_close(state)
    if branch.probe_phase:
        return _speak_probe(state, branch.probe_phase)
    return None


def _advance_probe_after_answer(
    state: EngineState,
    text: str,
) -> tuple[EngineState, list[Effect]]:
    step = advance_probe_phase(state, text)
    if step.action == ProbeAction.CONTINUE_LADDER:
        episode_resume = resume_episode_obligation(state)
        if episode_resume is not None and episode_resume.text:
            return _emit_speak(
                state,
                text=episode_resume.text,
                intent=episode_resume.intent or "episode_resume",
                slot=episode_resume.slot,
                marks_question=episode_resume.marks_question,
            )
        return _advance_after_fills(state, [])
    if step.action == ProbeAction.URGENT_CLOSE:
        return _emit_urgent_close(state)
    if step.action == ProbeAction.SPEAK_PROBE and step.probe_phase:
        return _speak_probe(state, step.probe_phase)
    if step.action == ProbeAction.SPEAK_SLOT and step.next_slot:
        if not can_ask_slot(state, step.next_slot):
            return _close_partial(state)
        ack = questions.wellness_ack(
            polarity=step.ack_polarity,
            value=state.wellness_concern or text,
        )
        question = questions.slot_question(step.next_slot, state=state)
        return _emit_speak(
            state,
            text=f"{ack} {question}".strip(),
            intent=f"check_{step.next_slot}",
            slot=step.next_slot,
            marks_question=True,
        )
    if step.action == ProbeAction.SPEAK_PLANS:
        if not can_ask_slot(state, "plans"):
            return _close_partial(state)
        question = questions.plans_question(state)
        return _emit_speak(
            state,
            text=f"Понимаю. {question}".strip(),
            intent="check_plans",
            slot="plans",
            marks_question=True,
        )
    return _advance_after_fills(state, [])


def _speak_probe(
    state: EngineState,
    phase: str,
    *,
    clarification: bool = False,
) -> tuple[EngineState, list[Effect]]:
    text = questions.probe_question(phase, clarification=clarification)
    intent = f"probe_{phase}"
    slot = f"probe_{phase}"
    return _emit_speak(
        state,
        text=text,
        intent=intent,
        slot=slot,
        marks_question=True,
    )


def _emit_summary(state: EngineState) -> tuple[EngineState, list[Effect]]:
    state.fsm_state = FsmState.SUMMARY
    state.summary_spoken = True
    state.bump_revision()
    return _emit_speak(
        state,
        text=questions._SUMMARY_TEXT,
        intent="summary",
        slot=None,
        marks_question=False,
    )


def _emit_urgent_close(state: EngineState) -> tuple[EngineState, list[Effect]]:
    state.fsm_state = FsmState.SUMMARY
    state.summary_spoken = True
    state.call_closed = True
    state.closing_reason = "urgent"
    state.bump_revision()
    return _emit_speak(
        state,
        text=questions._URGENT_CLOSE,
        intent="urgent_close",
        slot=None,
        marks_question=False,
    )


def _advance_after_fill(
    state: EngineState,
    filled_slot: str,
) -> tuple[EngineState, list[Effect]]:
    return _advance_after_fills(state, [filled_slot])


def _speak_slot_question(
    state: EngineState,
    slot: str,
    *,
    clarification: bool = False,
) -> tuple[EngineState, list[Effect]]:
    if not can_ask_slot(state, slot):
        return _close_partial(state)
    text = questions.slot_question(slot, clarification=clarification, state=state)
    intent = f"clarify_{slot}" if clarification else f"check_{slot}"
    return _emit_speak(
        state,
        text=text,
        intent=intent,
        slot=slot,
        marks_question=True,
    )


def _speak_repair(
    state: EngineState,
    slot: str,
) -> tuple[EngineState, list[Effect]]:
    delivered = state.delivered_question
    question_text = delivered.text if delivered else questions.slot_question(slot)
    text = questions.repair_response(question_text)
    state.bump_revision()
    gen_id = state.next_generation_id()
    gen = state.active_playout_generation + 1
    state.active_playout_generation = gen
    q = Question(
        question_id=delivered.question_id if delivered else gen_id,
        slot=slot,
        text=text,
        phase=QuestionPhase.PLANNED,
        intent="repair_repeat",
    )
    state.active_playout = q
    return state, [
        SpeakEffect(
            effect_id=_new_effect_id(),
            revision=state.revision,
            generation_id=gen_id,
            generation=gen,
            text=text,
            intent="repair_repeat",
            question_id=delivered.question_id if delivered else gen_id,
            slot=slot,
            marks_question=False,
        )
    ]


def _close_partial(state: EngineState) -> tuple[EngineState, list[Effect]]:
    if state.playing_question or state.planned_question:
        return state, []
    state.call_closed = True
    state.closing_reason = "partial_unresolved"
    state.fsm_state = FsmState.FINAL_CLASSIFICATION
    state.bump_revision()
    return _emit_speak(
        state,
        text=questions._PARTIAL_CLOSE,
        intent="partial_unresolved_close",
        slot=None,
        marks_question=False,
    )


def _on_delivery_deferred(
    state: EngineState,
    event: DeliveryDeferred,
) -> tuple[EngineState, list[Effect]]:
    if state.deferred_speak and state.deferred_speak.effect_id == event.effect_id:
        return state, []
    return state, []


def _on_effect_failed(
    state: EngineState,
    event: EffectFailed,
) -> tuple[EngineState, list[Effect]]:
    state.bump_revision()
    return state, []


def _on_speak_effect_stale(
    state: EngineState,
    event: SpeakEffectStale,
) -> tuple[EngineState, list[Effect]]:
    if state.deferred_speak and state.deferred_speak.effect_id == event.effect_id:
        state.deferred_speak = None
    intent = event.intent
    if (
        intent == "summary"
        and state.summary_spoken
        and state.fsm_state == FsmState.SUMMARY
        and not state.call_closed
    ):
        return _emit_speak(
            state,
            text=questions._SUMMARY_TEXT,
            intent="summary",
            slot=None,
            marks_question=False,
        )
    if intent == "goodbye_final" and state.call_closed:
        return _emit_speak(
            state,
            text=questions._GOODBYE_FINAL,
            intent="goodbye_final",
            slot=None,
            marks_question=False,
        )
    if intent == "goodbye_confirm" and state.awaiting_goodbye_confirm:
        return _emit_speak(
            state,
            text=questions._GOODBYE_CONFIRM,
            intent="goodbye_confirm",
            slot=None,
            marks_question=False,
        )
    if intent.startswith(("check_", "clarify_")):
        slot = intent.split("_", 1)[1]
        if slot and can_ask_slot(state, slot):
            return _speak_slot_question(
                state,
                slot,
                clarification=intent.startswith("clarify_"),
            )
    return state, []


def _on_timer_expired(state: EngineState, event: TimerExpired) -> tuple[EngineState, list[Effect]]:
    if _stale(state, event.revision):
        return state, []
    slot = state.waiting_on_slot
    if event.timer_id.startswith("wait-") and not slot:
        slot = event.timer_id.removeprefix("wait-")
    state.waiting_on_slot = None
    state.bump_revision()
    if not slot or state.fsm_state != FsmState.DAILY_CHECK:
        return state, []
    if slot.startswith("probe_"):
        phase = slot.removeprefix("probe_")
        return _speak_probe(state, phase, clarification=True)
    if not can_ask_slot(state, slot):
        return _close_partial(state)
    return _speak_slot_question(state, slot, clarification=True)


def _handle_closing_turn(
    state: EngineState,
    semantic,
) -> tuple[EngineState, list[Effect]] | None:
    if semantic.act == SemanticAct.REPAIR_REQUEST:
        return None
    if semantic.act == SemanticAct.BACKCHANNEL and not state.awaiting_goodbye_confirm:
        return None
    if semantic.act == SemanticAct.UNCLEAR and not state.awaiting_goodbye_confirm:
        return None
    text = semantic.source_quote.lower().strip()
    if semantic.act == SemanticAct.GOODBYE_CONFIRM or (
        state.awaiting_goodbye_confirm and _confirms_goodbye(text)
    ):
        state.goodbye_confirmed = True
        state.awaiting_goodbye_confirm = False
        state.fsm_state = FsmState.FINAL_CLASSIFICATION
        state.call_closed = True
        state.closing_reason = "goodbye"
        state.bump_revision()
        return _emit_speak(
            state,
            text=questions._GOODBYE_FINAL,
            intent="goodbye_final",
            slot=None,
            marks_question=False,
        )
    if semantic.act == SemanticAct.GOODBYE_REQUEST or any(
        marker in text for marker in questions._GOODBYE_MARKERS
    ):
        state.goodbye_count += 1
        if state.goodbye_count >= 2:
            state.goodbye_confirmed = True
            state.awaiting_goodbye_confirm = False
            state.fsm_state = FsmState.FINAL_CLASSIFICATION
            state.call_closed = True
            state.closing_reason = "goodbye"
            state.bump_revision()
            return _emit_speak(
                state,
                text=questions._GOODBYE_FINAL,
                intent="goodbye_final",
                slot=None,
                marks_question=False,
            )
        state.awaiting_goodbye_confirm = True
        state.fsm_state = FsmState.GOODBYE
        state.bump_revision()
        return _emit_speak(
            state,
            text=questions._GOODBYE_CONFIRM,
            intent="goodbye_confirm",
            slot=None,
            marks_question=False,
        )
    return None


def _confirms_goodbye(text: str) -> bool:
    return text in {"да", "ага", "угу", "конечно", "давайте", "ладно", "yes"}
