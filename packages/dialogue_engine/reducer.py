"""Single-writer reducer — synchronous, deterministic, no I/O."""

from __future__ import annotations

import uuid

from packages.contracts.enums import FsmState, SlotStatus
from packages.dialogue_engine import questions
from packages.dialogue_engine.effects import Effect, EndCallEffect, InterpretEffect, SpeakEffect, TimerEffect
from packages.dialogue_engine.events import (
    CallStarted,
    DeliveryDeferred,
    DialogueEvent,
    InterpretationCompleted,
    PlayoutCancelled,
    PlayoutCompleted,
    PlayoutStarted,
    SpeakEffectStale,
    TimerExpired,
    UserTurnReceived,
)
from packages.dialogue_engine.policy import (
    can_ask_slot,
    fill_from_semantic,
    mark_question_delivered,
    may_close_partial,
    release_reservation,
    reserve_question,
)
from packages.dialogue_engine.semantic import SemanticAct
from packages.dialogue_engine.state import (
    EngineState,
    OpeningState,
    Question,
    QuestionPhase,
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
    return state, []


def _tag_effects(effects: list[Effect], state: EngineState) -> list[Effect]:
    tagged: list[Effect] = []
    for eff in effects:
        if hasattr(eff, "model_copy"):
            tagged.append(
                eff.model_copy(update={"revision": state.revision, "effect_id": eff.effect_id or _new_effect_id()})
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
        text=questions.opening_speech(state.elder_display_name),
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
    if q is None or (event.question_id and q.question_id != event.question_id):
        return state, []
    delivered = q.model_copy(update={"phase": QuestionPhase.DELIVERED})
    state.delivered_question = delivered
    state.playing_question = None
    state.planned_question = None
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
    if event.effect_id and event.semantic is None:
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
            return state, []
        state.processing_turn_id = None
        state.processing_effect_id = None
        return _speak_repair(state, answer_slot or semantic.target_slot or "wellness")

    if semantic.act == SemanticAct.BACKCHANNEL:
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.bump_revision()
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
        return state, []

    if semantic.act == SemanticAct.UNCLEAR and answer_slot:
        count = state.slot_unclear_counts.get(answer_slot, 0) + 1
        state.slot_unclear_counts[answer_slot] = count
        state.processing_turn_id = None
        state.processing_effect_id = None
        if may_close_partial(state, answer_slot):
            return _close_partial(state)
        if can_ask_slot(state, answer_slot):
            return _speak_slot_question(state, answer_slot, clarification=True)
        return state, []

    filled = fill_from_semantic(state, semantic)
    if filled:
        state.processing_turn_id = None
        state.processing_effect_id = None
        return _advance_after_fill(state, filled)

    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    return state, []


def _advance_after_fill(
    state: EngineState,
    filled_slot: str,
) -> tuple[EngineState, list[Effect]]:
    state.delivered_question = None
    next_slot = state.next_open_slot()
    if next_slot is None:
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
    if not can_ask_slot(state, next_slot):
        return _close_partial(state)
    text = questions.slot_question(next_slot)
    if filled_slot == "wellness":
        val = state.slot_values.get("wellness", "")
        ack = questions.wellness_ack(value=val)
        text = f"{ack} {text}"
    intent = f"check_{next_slot}"
    return _emit_speak(
        state,
        text=text,
        intent=intent,
        slot=next_slot,
        marks_question=True,
    )


def _speak_slot_question(
    state: EngineState,
    slot: str,
    *,
    clarification: bool = False,
) -> tuple[EngineState, list[Effect]]:
    if not can_ask_slot(state, slot):
        return _close_partial(state)
    text = questions.slot_question(slot, clarification=clarification)
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
    gen_id = state.next_generation_id()
    gen = state.active_playout_generation + 1
    state.active_playout_generation = gen
    return state, [
        SpeakEffect(
            effect_id=_new_effect_id(),
            revision=state.revision,
            generation_id=gen_id,
            generation=gen,
            text=questions._PARTIAL_CLOSE,
            intent="partial_unresolved_close",
            marks_question=False,
        ),
        EndCallEffect(
            effect_id=_new_effect_id(),
            revision=state.revision,
            reason="partial_unresolved",
        ),
    ]


def _on_delivery_deferred(
    state: EngineState,
    event: DeliveryDeferred,
) -> tuple[EngineState, list[Effect]]:
    if state.deferred_speak and state.deferred_speak.effect_id == event.effect_id:
        return state, []
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
    if not can_ask_slot(state, slot):
        return _close_partial(state)
    return _speak_slot_question(state, slot, clarification=True)


def _handle_closing_turn(
    state: EngineState,
    semantic,
) -> tuple[EngineState, list[Effect]] | None:
    text = semantic.source_quote.lower().strip()
    if semantic.act == SemanticAct.GOODBYE_CONFIRM or _confirms_goodbye(text):
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
