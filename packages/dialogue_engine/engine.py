"""DialogueEngine — single writer for pilot daily-check conversations."""

from __future__ import annotations

import uuid
from collections import deque

from packages.contracts.enums import FsmState, GoalStatus, SlotStatus
from packages.contracts.turn import TurnProposal
from packages.dialogue.state import DialogueState
from packages.dialogue_engine.effects import Effect, EndCallEffect, InterpretEffect, SpeakEffect, TimerEffect
from packages.dialogue_engine.events import (
    CallStarted,
    DeliveryDeferred,
    InterpretationCompleted,
    PlayoutCancelled,
    PlayoutCompleted,
    PlayoutStarted,
    SpeakEffectStale,
    TimerExpired,
    UserTurnReceived,
)
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.semantic import SemanticTurn
from packages.dialogue_engine.state import EngineState, OpeningState


class DialogueEngine:
    """Owns conversation state. CallSession/CallActor emit events, drain effects."""

    def __init__(
        self,
        *,
        call_id: str,
        elder_display_name: str = "Анной Петровной",
    ) -> None:
        self.state = EngineState(
            call_id=call_id,
            elder_display_name=elder_display_name,
        )
        self._effect_queue: deque[Effect] = deque()
        self._started = False
        self._completed_playout_generations: set[int] = set()

    @property
    def revision(self) -> int:
        return self.state.revision

    def answer_context_slot(self) -> str | None:
        return self.state.answer_context_slot()

    def begin_interpret(self, turn_id: str) -> str:
        effect_id = f"ix-{uuid.uuid4().hex[:8]}"
        self.state.processing_turn_id = turn_id
        self.state.processing_effect_id = effect_id
        return effect_id

    def start(self) -> list[Effect]:
        if self._started:
            return []
        self._started = True
        return self._apply(CallStarted())

    def on_user_turn(
        self,
        turn_id: str,
        text: str,
        semantic: SemanticTurn | None = None,
        *,
        effect_id: str = "",
        defer: bool = False,
    ) -> list[Effect]:
        if defer or (effect_id and semantic is None):
            return self._apply(
                UserTurnReceived(
                    turn_id=turn_id,
                    text=text,
                    semantic=None,
                    effect_id=effect_id,
                    revision=self.state.revision,
                )
            )
        if semantic is None:
            return []
        return self._apply(
            UserTurnReceived(
                turn_id=turn_id,
                text=text,
                semantic=semantic,
                effect_id=effect_id,
                revision=self.state.revision,
            )
        )

    def on_interpretation_completed(
        self,
        turn_id: str,
        effect_id: str,
        semantic: SemanticTurn,
    ) -> list[Effect]:
        if turn_id != self.state.processing_turn_id:
            return []
        if self.state.processing_effect_id and effect_id != self.state.processing_effect_id:
            return []
        return self._apply(
            InterpretationCompleted(
                turn_id=turn_id,
                effect_id=effect_id,
                semantic=semantic,
                revision=self.state.revision,
            )
        )

    def on_playout_started(self, generation: int, question_id: str) -> list[Effect]:
        return self._apply(
            PlayoutStarted(
                generation=generation,
                question_id=question_id,
                revision=self.state.revision,
            )
        )

    def on_playout_completed(self, generation: int, question_id: str) -> list[Effect]:
        if generation in self._completed_playout_generations:
            return []
        self._completed_playout_generations.add(generation)
        return self._apply(
            PlayoutCompleted(
                generation=generation,
                question_id=question_id,
                revision=self.state.revision,
            )
        )

    def on_playout_cancelled(self, generation: int, question_id: str = "") -> list[Effect]:
        if generation in self._completed_playout_generations:
            return []
        return self._apply(
            PlayoutCancelled(
                generation=generation,
                question_id=question_id,
                revision=self.state.revision,
            )
        )

    def on_timer_expired(self, timer_id: str = "") -> list[Effect]:
        return self._apply(TimerExpired(timer_id=timer_id, revision=self.state.revision))

    def on_delivery_deferred(self, effect: SpeakEffect) -> list[Effect]:
        self.state.deferred_speak = effect
        return self._apply(
            DeliveryDeferred(effect_id=effect.effect_id, revision=effect.revision)
        )

    def on_speak_effect_stale(self, effect: SpeakEffect) -> list[Effect]:
        return self._apply(
            SpeakEffectStale(
                effect_id=effect.effect_id,
                intent=effect.intent,
                generation=effect.generation,
                revision=effect.revision,
            )
        )

    def is_speak_effect_valid(self, effect: SpeakEffect) -> bool:
        if effect.revision != self.state.revision:
            return False
        if effect.generation != self.state.active_playout_generation:
            return False
        return True

    def clear_deferred_speak(self) -> None:
        self.state.deferred_speak = None

    def drain_speak_effects(self) -> list[SpeakEffect]:
        speaks: list[SpeakEffect] = []
        while self._effect_queue:
            eff = self._effect_queue.popleft()
            if isinstance(eff, SpeakEffect):
                speaks.append(eff)
        return speaks

    def pop_speak_effect(self) -> SpeakEffect | None:
        while self._effect_queue:
            eff = self._effect_queue.popleft()
            if isinstance(eff, SpeakEffect):
                return eff
        return None

    def pop_timer_effect(self) -> TimerEffect | None:
        kept: deque[Effect] = deque()
        found: TimerEffect | None = None
        while self._effect_queue:
            eff = self._effect_queue.popleft()
            if found is None and isinstance(eff, TimerEffect):
                found = eff
            else:
                kept.append(eff)
        self._effect_queue = kept
        return found

    def peek_pending_speak_effects(self) -> list[SpeakEffect]:
        return [e for e in self._effect_queue if isinstance(e, SpeakEffect)]

    def effect_to_proposal(self, effect: SpeakEffect, turn_id: int, legacy: DialogueState) -> TurnProposal:
        goal_id = None
        if effect.slot:
            goal_id = legacy.ensure_goal(effect.slot).goal_id
        return TurnProposal(
            turn_id=turn_id,
            generation_id=effect.generation_id,
            speech=effect.text,
            intent=effect.intent,
            fsm_state=legacy.fsm_state,
            mandatory_remaining=legacy.mandatory_remaining(),
            question_goal_id=goal_id,
        )

    def sync_to_legacy(self, legacy: DialogueState) -> None:
        eng = self.state
        legacy.fsm_state = eng.fsm_state
        legacy.first_user_turn_received = eng.first_user_turn_received
        legacy.opening_delivered = eng.opening_state == OpeningState.DELIVERED
        legacy.opening_play_count = eng.opening_play_count

        for slot, status in eng.slots.items():
            legacy.slots[slot] = status
            if status == SlotStatus.FILLED and slot in eng.slot_values:
                from packages.dialogue.facts import FactRecord

                val = eng.slot_values[slot]
                prev = legacy.facts.get(slot)
                rev = (prev.revision + 1) if prev else 1
                legacy.facts[slot] = FactRecord(
                    field=slot,
                    value=val,
                    source_quote=val,
                    turn_id=eng.turn_seq,
                    revision=rev,
                )
                legacy.mandatory_checks[slot] = True
                goal = legacy.ensure_goal(slot)
                goal.status = GoalStatus.ANSWERED
                goal.automatic_attempts_used = eng.ensure_goal(slot).delivered_attempts

        if eng.delivered_question:
            legacy.delivered_answer_slot = eng.delivered_question.slot
            legacy.pending_slot = eng.delivered_question.slot
            legacy.pending_question = eng.delivered_question.text
            legacy.pending_question_delivered = True
        elif eng.playing_question:
            legacy.pending_slot = eng.playing_question.slot
            legacy.pending_question = eng.playing_question.text
            legacy.pending_question_delivered = False
        elif eng.planned_question:
            legacy.pending_slot = eng.planned_question.slot
            legacy.pending_question = eng.planned_question.text
            legacy.pending_question_delivered = False
        else:
            legacy.pending_slot = eng.next_open_slot()
            legacy.pending_question_delivered = False

        legacy.slot_unclear_counts = dict(eng.slot_unclear_counts)
        legacy.waiting_on_goal = eng.waiting_on_slot
        legacy.summary_spoken = eng.summary_spoken
        legacy.awaiting_goodbye_confirm = eng.awaiting_goodbye_confirm
        legacy.goodbye_confirmed = eng.goodbye_confirmed
        legacy.goodbye_count = eng.goodbye_count

        if eng.call_closed:
            legacy.call_ended_early = True
            legacy.final_action_done = True
            if eng.closing_reason == "goodbye":
                from packages.contracts.core import TerminationReason

                legacy.termination_reason = TerminationReason.COMPLETED
            else:
                legacy.goodbye_confirmed = True
                legacy.fsm_state = FsmState.FINAL_CLASSIFICATION
                from packages.contracts.core import TerminationReason

                legacy.termination_reason = TerminationReason.PARTIAL

        legacy.bump_version()

    def _apply(self, event) -> list[Effect]:
        self.state, effects = reduce(self.state, event)
        for eff in effects:
            self._effect_queue.append(eff)
        return effects
