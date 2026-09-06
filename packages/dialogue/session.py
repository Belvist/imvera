"""Unified call session — single entry for user events and policy ordering."""

from pydantic import BaseModel, Field

from packages.contracts.enums import FsmState, RiskLevel
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.status import SafetySnapshot
from packages.contracts.turn import TurnProposal, ValidatedTurn
from packages.dialogue.fsm import CallFsm
from packages.dialogue.interpretation import (
    UserInterpretation,
    interpret_user_turn,
    to_turn_interpretation,
)
from packages.dialogue.planner import Planner
from packages.dialogue.state import DialogueState
from packages.dialogue.validator import Validator
from packages.safety import SafetyEngine

_RED_INTERRUPT_STATES = frozenset(
    {
        FsmState.RED_SIGNAL,
        FsmState.CONFIRM_SITUATION,
        FsmState.INCIDENT_REQUESTED,
        FsmState.ESCALATION_HANDOFF,
        FsmState.FINAL_CLASSIFICATION,
    }
)


class SessionTurnResult(BaseModel):
    user_text: str
    interpretation: UserInterpretation
    turn_contract: TurnInterpretation
    proposal: TurnProposal
    validated: ValidatedTurn
    safety: SafetySnapshot = Field(default_factory=SafetySnapshot)


class CallSession:
    """One conversation — owns state, safety observations, and turn sequencing."""

    def __init__(self, call_id: str, elder_display_name: str = "Анной Петровной") -> None:
        self.state = DialogueState(call_id=call_id, elder_display_name=elder_display_name)
        self.safety = SafetySnapshot()
        self.turn_id = 0
        self._generation_seq = 0

    def _next_generation_id(self) -> str:
        self._generation_seq += 1
        return f"g{self._generation_seq}"

    def start(self) -> SessionTurnResult:
        self.turn_id += 1
        gen = self._next_generation_id()
        proposal = Planner.plan_vera_turn(self.state, self.turn_id, gen)
        validated = Validator.validate(proposal)
        from packages.contracts.enums import AnswerJudgement, DialogueAct

        empty_interp = UserInterpretation(
            judgement=AnswerJudgement.NO_ANSWER,
            dialogue_act=DialogueAct.UNCLEAR,
        )
        return SessionTurnResult(
            user_text="",
            interpretation=empty_interp,
            turn_contract=TurnInterpretation(
                call_id=self.state.call_id,
                turn_id=self.turn_id,
                raw_text="",
                dialogue_act=DialogueAct.UNCLEAR,
                judgement=AnswerJudgement.NO_ANSWER,
                state_version=self.state.state_version,
            ),
            proposal=proposal,
            validated=validated,
            safety=self.safety,
        )

    def handle_user_text(self, user_text: str) -> SessionTurnResult:
        interp = interpret_user_turn(self.state, user_text)
        SafetyEngine.ingest_transcript(self.safety, user_text)

        if (
            self.safety.active_risk == RiskLevel.RED
            and self.state.fsm_state not in _RED_INTERRUPT_STATES
        ):
            CallFsm.interrupt_red(self.state)
            self.state.bump_version()

        self.turn_id += 1
        gen = self._next_generation_id()
        proposal = Planner.plan_after_user(
            self.state,
            user_text,
            gen,
            self.turn_id,
            interp=interp,
        )
        validated = Validator.validate(proposal)
        contract = to_turn_interpretation(self.state, self.turn_id, user_text, interp)
        return SessionTurnResult(
            user_text=user_text,
            interpretation=interp,
            turn_contract=contract,
            proposal=proposal,
            validated=validated,
            safety=self.safety,
        )

    def say(self, user_text: str) -> str:
        """Convenience for text runner — returns Vera's validated speech."""
        if self.turn_id == 0:
            return self.start().validated.speech
        return self.handle_user_text(user_text).validated.speech
