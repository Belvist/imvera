"""DialogueEngine — single writer for pilot daily-check conversations."""

from __future__ import annotations

import uuid

from packages.contracts.enums import FsmState, GoalStatus, SlotStatus
from packages.contracts.mandatory import PILOT_SLOT_CHECKS
from packages.contracts.turn import TurnProposal
from packages.dialogue.state import DialogueState
from packages.dialogue_engine.delivery import Decision, EffectDispatcher, EffectOutbox
from packages.dialogue_engine.delivery.scope import speak_scope_for, timer_scope_for
from packages.dialogue_engine.effects import Effect, EndCallEffect, InterpretEffect, SpeakEffect, TimerEffect
from packages.dialogue_engine.events import (
    CallStarted,
    DeliveryDeferred,
    EffectFailed,
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
        prior_call_context: dict[str, str] | None = None,
    ) -> None:
        self.state = EngineState(
            call_id=call_id,
            elder_display_name=elder_display_name,
            prior_call_context=dict(prior_call_context or {}),
            follow_up_opening=bool(prior_call_context),
        )
        self._outbox = EffectOutbox(call_id=call_id)
        self._dispatcher = EffectDispatcher(self._outbox)
        self._started = False
        self._completed_playout_generations: set[int] = set()

    @property
    def outbox(self) -> EffectOutbox:
        return self._outbox

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
        if self._outbox.get_record(effect.effect_id) is None:
            enriched = self._enrich_effects([effect])
            if enriched:
                self._dispatcher.accept(Decision.from_effects(self.state.revision, enriched))
                effect = enriched[0]  # type: ignore[assignment]
        self.state.deferred_speak = effect
        self._outbox.defer_speak(effect.effect_id)
        return self._apply(
            DeliveryDeferred(effect_id=effect.effect_id, revision=effect.revision)
        )

    def on_speak_effect_stale(self, effect: SpeakEffect) -> list[Effect]:
        semantic_key = effect.semantic_scope_id or f"{effect.intent}:{effect.generation_id}"
        if not self._outbox.reissue_allowed(semantic_key):
            self._outbox.mark_stale(effect.effect_id, reason="reissue_loop")
            return []
        self._outbox.track_reissue(semantic_key)
        self._outbox.mark_stale(effect.effect_id)
        return self._apply(
            SpeakEffectStale(
                effect_id=effect.effect_id,
                intent=effect.intent,
                generation=effect.generation,
                revision=effect.revision,
            )
        )

    def on_effect_failed(self, effect_id: str, *, stage: str, error: str = "") -> list[Effect]:
        self._outbox.mark_failed(effect_id, stage=stage, error=error)
        return self._apply(
            EffectFailed(
                effect_id=effect_id,
                stage=stage,  # type: ignore[arg-type]
                error=error,
                revision=self.state.revision,
            )
        )

    def is_speak_effect_valid(self, effect: SpeakEffect) -> bool:
        return self._outbox.is_speak_valid(effect, self.state)

    def clear_deferred_speak(self) -> None:
        self.state.deferred_speak = None
        self._outbox.clear_deferred_speak()

    def drain_speak_effects(self) -> list[SpeakEffect]:
        """Claim all remaining speak effects (typed outbox index — timers untouched)."""
        return self._dispatcher.drain_speaks()

    def pop_speak_effect(self) -> SpeakEffect | None:
        """Claim next speak from outbox. Timers/hangups stay in separate indexes."""
        return self._dispatcher.claim_speak()

    def pop_timer_effect(self) -> TimerEffect | None:
        """Claim next timer from outbox. Never mixed with speak pop."""
        return self._dispatcher.claim_timer()

    def pop_hangup_effect(self) -> EndCallEffect | None:
        return self._dispatcher.claim_hangup()

    def peek_pending_speak_effects(self) -> list[SpeakEffect]:
        return self._outbox.peek_pending_speaks()

    def slot_mandatory_remaining(self) -> list[str]:
        """Daily-check slots only — legacy identity/consent/can_talk are not engine-owned."""
        eng = self.state
        return [
            slot
            for slot in PILOT_SLOT_CHECKS
            if slot not in eng.skipped_slots
            and eng.slots.get(slot) != SlotStatus.FILLED
        ]

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
            mandatory_remaining=self.slot_mandatory_remaining(),
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
        enriched = self._enrich_effects(effects)
        if enriched:
            self._dispatcher.accept(Decision.from_effects(self.state.revision, enriched))
        return enriched

    def _enrich_effects(self, effects: list[Effect]) -> list[Effect]:
        enriched: list[Effect] = []
        for eff in effects:
            if isinstance(eff, InterpretEffect):
                enriched.append(eff)
                continue
            eid = eff.effect_id or f"fx-{uuid.uuid4().hex[:8]}"
            if isinstance(eff, SpeakEffect):
                scope = eff.semantic_scope_id or speak_scope_for(
                    intent=eff.intent,
                    generation_id=eff.generation_id,
                    slot=eff.slot,
                    marks_question=eff.marks_question,
                )
                enriched.append(
                    eff.model_copy(
                        update={
                            "effect_id": eid,
                            "revision": eff.revision or self.state.revision,
                            "semantic_scope_id": scope,
                        }
                    )
                )
            elif isinstance(eff, TimerEffect):
                qid = ""
                if self.state.delivered_question:
                    qid = self.state.delivered_question.question_id
                scope = eff.semantic_scope_id or timer_scope_for(
                    timer_id=eff.timer_id,
                    question_id=qid,
                )
                enriched.append(
                    eff.model_copy(
                        update={
                            "effect_id": eid,
                            "revision": eff.revision or self.state.revision,
                            "semantic_scope_id": scope,
                        }
                    )
                )
            elif isinstance(eff, EndCallEffect):
                enriched.append(
                    eff.model_copy(
                        update={
                            "effect_id": eid,
                            "revision": eff.revision or self.state.revision,
                        }
                    )
                )
            else:
                enriched.append(eff)
        return enriched
