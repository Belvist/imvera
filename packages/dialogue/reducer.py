"""State reducer — sole application of validated user meaning to DialogueState."""

from packages.contracts.core import TerminationReason
from packages.contracts.enums import AnswerJudgement, ConsentState, FsmState, GoalStatus, SlotStatus
from packages.dialogue.facts import FactRecord
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.state import DialogueState


class DialogueReducer:
    @staticmethod
    def apply(
        state: DialogueState,
        interp: UserInterpretation,
        turn_id: int,
        *,
        utterance_id: str = "",
        apply_facts: bool = True,
    ) -> DialogueState:
        if interp.sets_consent == ConsentState.DECLINED:
            state.consent_declined = True
            state.mandatory_checks["consent"] = False
            state.fsm_state = FsmState.FINAL_CLASSIFICATION
            state.call_ended_early = True
            state.final_action_done = True
            state.goodbye_confirmed = True
            state.termination_reason = TerminationReason.CONSENT_DECLINED
            state.bump_version()
            return state

        if interp.sets_consent == ConsentState.ACTIVE:
            state.mandatory_checks["consent"] = True
            state.consent_declined = False

        if interp.confirms_identity:
            state.mandatory_checks["identity"] = True

        if interp.confirms_can_talk:
            state.mandatory_checks["can_talk"] = True

        if not apply_facts:
            return state

        if interp.fact_candidates:
            for cand in interp.fact_candidates:
                DialogueReducer._commit_fact(
                    state,
                    cand.field,
                    cand.value,
                    cand.source_quote,
                    turn_id,
                    utterance_id=utterance_id,
                    negated=cand.negated,
                )
            if state.pending_slot and state.pending_slot in state.facts:
                filled_slot = state.pending_slot
                goal = state.get_goal(filled_slot)
                if goal is not None:
                    goal.status = GoalStatus.ANSWERED
                state.slots[filled_slot] = SlotStatus.FILLED
                state.mandatory_checks[filled_slot] = True
                state.pending_slot = None
                state.pending_question = None
                state.pending_question_delivered = False
                state.waiting_on_goal = None
            state.bump_version()
        elif (
            interp.fills_pending_slot
            and state.pending_slot
            and state.pending_slot in state.slots
            and interp.judgement == AnswerJudgement.VALID
        ):
            slot = state.pending_slot
            value = interp.slot_value or ""
            DialogueReducer._commit_fact(
                state, slot, value, value, turn_id, utterance_id=utterance_id
            )
            state.pending_slot = None
            state.pending_question = None
            state.pending_question_delivered = False
            state.bump_version()

        return state

    @staticmethod
    def _commit_fact(
        state: DialogueState,
        field: str,
        value: str,
        source_quote: str,
        turn_id: int,
        *,
        utterance_id: str = "",
        negated: bool = False,
        temporal_scope: str = "now",
        subject: str = "elder",
    ) -> None:
        prev = state.facts.get(field)
        revision = (prev.revision + 1) if prev else 1
        state.facts[field] = FactRecord(
            field=field,
            value=value,
            source_quote=source_quote,
            turn_id=turn_id,
            source_utterance_id=utterance_id,
            subject=subject,
            temporal_scope=temporal_scope,
            revision=revision,
            negated=negated,
        )
        state.slots[field] = SlotStatus.FILLED
        goal = state.get_goal(field)
        if goal is not None:
            goal.status = GoalStatus.ANSWERED
        state.mandatory_checks[field] = True
        state.slot_unclear_counts.pop(field, None)
