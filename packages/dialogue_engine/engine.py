"""DialogueEngine — single writer for pilot daily-check conversations."""

from __future__ import annotations

import uuid

from packages.contracts.enums import FsmState, GoalStatus, SlotStatus
from packages.contracts.mandatory import PILOT_SLOT_CHECKS
from packages.contracts.turn import TurnProposal
from packages.dialogue.state import DialogueState
from packages.dialogue_engine.delivery import Decision, EffectDispatcher, EffectOutbox
from packages.dialogue_engine.delivery.scope import speak_scope_for, timer_scope_for
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
    EffectFailed,
    FalseAlarmResolved,
    InterpretationCompleted,
    PlayoutCancelled,
    PlayoutCompleted,
    PlayoutStarted,
    SafetyInterrupt,
    SpeakEffectStale,
    TimerExpired,
    UserTurnReceived,
)
from packages.dialogue_engine.mission import CallMission
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.semantic import SemanticTurn
from packages.dialogue_engine.state import EngineState, OpeningState
from packages.dialogue_engine.turn_understanding import RichUserTurn


class DialogueEngine:
    """Owns conversation state. CallSession/CallActor emit events, drain effects."""

    def __init__(
        self,
        *,
        call_id: str,
        elder_display_name: str = "Анной Петровной",
        client_id: str = "",
        prior_call_context: dict[str, str] | None = None,
        mission: CallMission | None = None,
        mission_understanding_provider: object | None = None,
    ) -> None:
        from packages.dialogue_engine.mission_seed import apply_mission_to_state, resolve_mission

        self.mission = resolve_mission(mission)
        self.state = EngineState(
            call_id=call_id,
            elder_display_name=elder_display_name,
            client_id=client_id,
            prior_call_context=dict(prior_call_context or {}),
            follow_up_opening=bool(prior_call_context),
        )
        apply_mission_to_state(self.state, self.mission)
        self.state.target_display_name = elder_display_name
        self.mission_understanding_provider = mission_understanding_provider
        self._outbox = EffectOutbox(call_id=call_id)
        self._dispatcher = EffectDispatcher(self._outbox)
        self._started = False
        self._completed_playout_generations: set[int] = set()

    def build_rich_turn(
        self, text: str, *, utterance_id: str,
        act_candidate: SemanticTurn | None = None,
        candidate_confident: bool = False,
    ) -> RichUserTurn:
        """Canonical SDK understanding; models supply candidates, never state."""
        from packages.dialogue_engine.turn_understanding import TurnUnderstandingV2

        return TurnUnderstandingV2().resolve(
            text,
            utterance_id=utterance_id,
            engine_state=self.state,
            mission_provider=self.mission_understanding_provider,
            act_candidate=act_candidate,
            candidate_confident=candidate_confident,
        ).turn

    @property
    def outbox(self) -> EffectOutbox:
        return self._outbox

    @property
    def revision(self) -> int:
        return self.state.revision

    def answer_context_slot(self) -> str | None:
        return self.state.answer_context_slot()

    def pending_slot_name(self) -> str | None:
        """Engine mirror of the synced legacy pending_slot (sync_to_legacy).

        Delivered → playing → planned slot, else next open slot. Read-only;
        proven equal by tests/test_engine_pending_accessors.py. Question text
        and delivered_answer_slot are NOT mirrored: legacy keeps them stale
        after the engine question clears, so blind migration would change
        echo/fallback behavior (documented Cut-1 boundary).
        """
        state = self.state
        if state.delivered_question is not None:
            return state.delivered_question.slot
        if state.playing_question is not None:
            return state.playing_question.slot
        if state.planned_question is not None:
            return state.planned_question.slot
        return state.next_open_slot()

    def pending_question_text(self) -> str | None:
        """Current engine question text, None when none pending.

        Unlike the legacy mirror (which keeps the last text after clear),
        this reports the live question only. Cut 4c: used for echo
        candidates where staleness would misattribute old questions.
        """
        state = self.state
        if state.delivered_question is not None:
            return state.delivered_question.text
        if state.playing_question is not None:
            return state.playing_question.text
        if state.planned_question is not None:
            return state.planned_question.text
        return None

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
        rich_turn: RichUserTurn | None = None,
        effect_id: str = "",
        defer: bool = False,
    ) -> list[Effect]:
        if defer or (effect_id and semantic is None and rich_turn is None):
            return self._apply(
                UserTurnReceived(
                    turn_id=turn_id,
                    text=text,
                    semantic=None,
                    rich_turn=None,
                    effect_id=effect_id,
                    revision=self.state.revision,
                )
            )
        if rich_turn is not None:
            return self._apply(
                UserTurnReceived(
                    turn_id=turn_id,
                    text=text,
                    semantic=None,
                    rich_turn=rich_turn,
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
                rich_turn=None,
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

    def on_safety_interrupt(
        self,
        *,
        quote: str,
        episode_id: str | None = None,
        level: str = "RED",
    ) -> list[Effect]:
        return self._apply(
            SafetyInterrupt(
                level="RED" if level.upper() == "RED" else "YELLOW",
                quote=quote,
                episode_id=episode_id,
                revision=self.state.revision,
            )
        )

    def resolve_false_alarm(self, episode_id: str | None = None) -> None:
        """Exit red handling after a confirmed false alarm (COMMIT 4)."""
        self._apply(
            FalseAlarmResolved(
                episode_id=episode_id,
                revision=self.state.revision,
            )
        )

    def on_timer_expired(
        self, timer_id: str = "", uplink_frames: int | None = None
    ) -> list[Effect]:
        return self._apply(
            TimerExpired(
                timer_id=timer_id,
                revision=self.state.revision,
                uplink_frames=uplink_frames,
            )
        )

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

    def drain_action_policy_shadow_records(self) -> list[dict]:
        """Return and clear ephemeral ActionPolicy shadow records (CallSession persists)."""
        from packages.dialogue_engine.action_policy_shadow_buffer import (
            drain_shadow_records,
        )

        return drain_shadow_records(self.state)

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
        """Daily-check slots that still block close — optional background ≠ mandatory."""
        eng = self.state
        if not eng.mandatory_background_goals:
            required = eng.required_background_goals
            return [
                slot
                for slot in PILOT_SLOT_CHECKS
                if slot in required
                and slot not in eng.skipped_slots
                and eng.slots.get(slot) != SlotStatus.FILLED
            ]
        return [
            slot
            for slot in PILOT_SLOT_CHECKS
            if slot not in eng.skipped_slots
            and eng.slots.get(slot) != SlotStatus.FILLED
        ]

    def effect_to_proposal_legacy(
        self, effect: SpeakEffect, turn_id: int, legacy: DialogueState
    ) -> TurnProposal:
        """Pre-Cut-4a builder via the legacy mirror (parity reference only)."""
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

    def effect_to_proposal(self, effect: SpeakEffect, turn_id: int) -> TurnProposal:
        """Engine-native proposal (Cut 4a). fsm/mandatory already engine-owned;
        question_goal_id uses the engine goal contract (slot-string ids, NOT
        legacy random uuids) — downstream consumers use it opaquely."""
        goal_id = None
        if effect.slot:
            goal_id = self.state.ensure_goal(effect.slot).goal_id or effect.slot
        return TurnProposal(
            turn_id=turn_id,
            generation_id=effect.generation_id,
            speech=effect.text,
            intent=effect.intent,
            fsm_state=self.state.fsm_state,
            mandatory_remaining=self.slot_mandatory_remaining(),
            question_goal_id=goal_id,
        )

    def sync_to_legacy(self, legacy: DialogueState) -> None:
        eng = self.state
        legacy.fsm_state = eng.fsm_state
        legacy.first_user_turn_received = eng.first_user_turn_received
        legacy.opening_delivered = eng.opening_state == OpeningState.DELIVERED
        legacy.opening_play_count = eng.opening_play_count
        legacy.risk_handling = eng.risk_handling
        if eng.risk_episode_id:
            legacy.risk_episode_id = eng.risk_episode_id

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
