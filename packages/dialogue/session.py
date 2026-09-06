"""Unified call session — single entry for user events and policy ordering."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from packages.contracts.enums import FsmState, RiskLevel
from packages.contracts.events import CallEvent
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.status import SafetySnapshot
from packages.contracts.turn import TurnProposal, ValidatedTurn
from packages.core.store import CallRecordStore, observation_from_fact
from packages.dialogue.fsm import CallFsm
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.interpreter import Interpreter
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
    safety: SafetySnapshot
    observation_ids: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class CallSession:
    """One conversation — owns state, safety observations, persistence, and turns."""

    def __init__(
        self,
        call_id: str,
        elder_display_name: str = "Анной Петровной",
        family_id: str = "",
        store: CallRecordStore | None = None,
        interpreter: Interpreter | None = None,
    ) -> None:
        self.state = DialogueState(
            call_id=call_id,
            elder_display_name=elder_display_name,
            family_id=family_id,
        )
        self.safety = SafetySnapshot()
        self.store = store or CallRecordStore()
        self.interpreter = interpreter or Interpreter()
        self.turn_id = 0
        self._generation_seq = 0
        self._obs_seq = 0
        self._event_seq = 0

    def _next_generation_id(self) -> str:
        self._generation_seq += 1
        return f"g{self._generation_seq}"

    def _append_event(self, event_type: str, payload: dict) -> None:
        self._event_seq += 1
        event = CallEvent(
            event_id=f"{self.state.call_id}-ev-{self._event_seq}",
            call_id=self.state.call_id,
            sequence_no=self._event_seq,
            occurred_at=datetime.now(UTC),
            event_type=event_type,
            payload=payload,
            idempotency_key=f"{self.state.call_id}:{event_type}:{self._event_seq}",
        )
        self.store.append_event(event)

    def _persist_facts(self, turn_id: int) -> list[str]:
        ids: list[str] = []
        for fact in self.state.facts.values():
            self._obs_seq += 1
            obs = observation_from_fact(self.state.call_id, turn_id, fact, self._obs_seq)
            if self.store.save_observation(obs):
                ids.append(obs.observation_id)
        return ids

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
        contract = TurnInterpretation(
            call_id=self.state.call_id,
            turn_id=self.turn_id,
            raw_text="",
            dialogue_act=DialogueAct.UNCLEAR,
            judgement=AnswerJudgement.NO_ANSWER,
            state_version=0,
        )
        self._append_event("CALL_STARTED", {"family_id": self.state.family_id})
        return SessionTurnResult(
            user_text="",
            interpretation=empty_interp,
            turn_contract=contract,
            proposal=proposal,
            validated=validated,
            safety=self.safety.model_copy(deep=True),
        )

    def handle_user_text(self, user_text: str) -> SessionTurnResult:
        next_turn = self.turn_id + 1
        interp, contract = self.interpreter.interpret(self.state, user_text, next_turn)

        SafetyEngine.ingest_transcript(self.safety, user_text)
        if (
            self.safety.active_risk == RiskLevel.RED
            and self.state.fsm_state not in _RED_INTERRUPT_STATES
        ):
            CallFsm.interrupt_red(self.state, source_quote=user_text.strip())
            self._append_event(
                "RED_SIGNAL",
                {"quote": user_text.strip(), "turn_id": next_turn},
            )

        self.turn_id = next_turn
        gen = self._next_generation_id()
        proposal = Planner.plan_after_user(
            self.state,
            user_text,
            gen,
            self.turn_id,
            interp=interp,
        )
        validated = Validator.validate(proposal)
        observation_ids = self._persist_facts(self.turn_id)

        if self.state.is_terminal() and self.state.final_action_done:
            self._append_event("CALL_ENDED", {"partial": bool(self.state.mandatory_remaining())})

        safety_snapshot = self.safety.model_copy(deep=True)
        return SessionTurnResult(
            user_text=user_text,
            interpretation=interp,
            turn_contract=contract,
            proposal=proposal,
            validated=validated,
            safety=safety_snapshot,
            observation_ids=observation_ids,
        )

    def get_persisted_result(self):

        return self.store.get_call_result(self.state.call_id)

    def say(self, user_text: str) -> str:
        """Convenience for text runner — returns Vera's validated speech."""
        if self.turn_id == 0:
            return self.start().validated.speech
        return self.handle_user_text(user_text).validated.speech
