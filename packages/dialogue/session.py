"""Unified call session — single entry for user events and policy ordering."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from packages.contracts.core import CallRecordStore, CallResultSnapshot
from packages.contracts.enums import AnswerJudgement, DialogueAct, FsmState, RiskLevel
from packages.contracts.events import CallEvent
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.status import SafetySnapshot
from packages.contracts.turn import TurnProposal, ValidatedTurn
from packages.core import create_call_record_store, observation_from_fact, observation_from_risk
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
    persist_ok: bool = True
    persist_error: str | None = None

    model_config = {"frozen": True}


class CallSession:
    def __init__(
        self,
        call_id: str,
        elder_display_name: str = "Анной Петровной",
        family_id: str = "",
        store: CallRecordStore | None = None,
        interpreter: Interpreter | None = None,
    ) -> None:
        if not family_id:
            raise ValueError("family_id is required for product calls")
        self.state = DialogueState(
            call_id=call_id,
            elder_display_name=elder_display_name,
            family_id=family_id,
        )
        self.safety = SafetySnapshot()
        self.store = store or create_call_record_store()
        self.interpreter = interpreter or Interpreter()
        self.turn_id = 0
        self._generation_seq = 0
        self._obs_seq = 0
        self._event_seq = 0
        self._persisted_obs_ids: list[str] = []
        self._persisted_keys: set[str] = set()

    def _next_generation_id(self) -> str:
        self._generation_seq += 1
        return f"g{self._generation_seq}"

    def _append_event(
        self,
        event_type: str,
        payload: dict,
        *,
        idempotency_key: str | None = None,
    ) -> bool:
        self._event_seq += 1
        key = idempotency_key or f"{self.state.call_id}:{event_type}:{self._event_seq}"
        event = CallEvent(
            event_id=f"{self.state.call_id}-ev-{self._event_seq}",
            call_id=self.state.call_id,
            sequence_no=self._event_seq,
            occurred_at=datetime.now(UTC),
            event_type=event_type,
            payload=payload,
            idempotency_key=key,
        )
        return self.store.append_event(event, self.state.family_id).ok

    def _snapshot(self) -> CallResultSnapshot:
        facts = {k: v.value for k, v in self.state.facts.items()}
        quotes = {k: v.source_quote for k, v in self.state.facts.items()}
        return CallResultSnapshot(
            call_id=self.state.call_id,
            family_id=self.state.family_id,
            fsm_state=self.state.fsm_state,
            facts=facts,
            fact_quotes=quotes,
            observations=list(self._persisted_obs_ids),
            partial=bool(self.state.mandatory_remaining()),
            call_ended=self.state.call_finalized,
            termination_reason=self.state.termination_reason,
        )

    def _finalize_call_if_needed(self) -> tuple[bool, str | None]:
        if not self.state.final_action_done or self.state.call_finalized:
            return True, None
        snap = self._snapshot().model_copy(update={"call_ended": True})
        result = self.store.finalize_call(snap)
        if not result.ok:
            return False, result.error
        self.state.call_finalized = True
        self._append_event(
            "CALL_ENDED",
            {
                "partial": snap.partial,
                "termination_reason": (
                    snap.termination_reason.value if snap.termination_reason else None
                ),
            },
            idempotency_key=f"{self.state.call_id}:CALL_ENDED",
        )
        return True, None

    def _persist_new_facts(self, turn_id: int) -> tuple[list[str], bool, str | None]:
        ids: list[str] = []
        for fact in self.state.facts.values():
            self._obs_seq += 1
            obs = observation_from_fact(self.state.call_id, turn_id, fact, self._obs_seq)
            if obs.idempotency_key in self._persisted_keys:
                continue
            result = self.store.save_observation(obs, self.state.family_id)
            if not result.ok:
                return ids, False, result.error
            self._persisted_keys.add(obs.idempotency_key)
            ids.append(obs.observation_id)
            self._persisted_obs_ids.append(obs.observation_id)
        return ids, True, None

    def _persist_risk(self, turn_id: int, quote: str) -> tuple[str | None, bool, str | None]:
        self._obs_seq += 1
        obs = observation_from_risk(
            self.state.call_id,
            turn_id,
            quote,
            self._obs_seq,
            self.state.risk_episode_id,
        )
        if obs.idempotency_key in self._persisted_keys:
            return obs.observation_id, True, None
        result = self.store.save_observation(obs, self.state.family_id)
        if not result.ok:
            return None, False, result.error
        self._persisted_keys.add(obs.idempotency_key)
        self._persisted_obs_ids.append(obs.observation_id)
        return obs.observation_id, True, None

    def start(self) -> SessionTurnResult:
        ensure = self.store.ensure_call(self.state.call_id, self.state.family_id)
        self.turn_id += 1
        gen = self._next_generation_id()
        proposal = Planner.plan_vera_turn(self.state, self.turn_id, gen)
        validated = Validator.validate(proposal)
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
            interpretation=UserInterpretation(
                judgement=AnswerJudgement.NO_ANSWER,
                dialogue_act=DialogueAct.UNCLEAR,
            ),
            turn_contract=contract,
            proposal=proposal,
            validated=validated,
            safety=self.safety.model_copy(deep=True),
            persist_ok=ensure.ok,
            persist_error=ensure.error,
        )

    def handle_user_text(
        self,
        user_text: str,
        *,
        interp: UserInterpretation | None = None,
        contract: TurnInterpretation | None = None,
    ) -> SessionTurnResult:
        if self.state.call_finalized:
            gen = self._next_generation_id()
            proposal = Planner._terminal_noop(self.state, self.turn_id, gen)
            validated = Validator.validate(proposal)
            return SessionTurnResult(
                user_text=user_text,
                interpretation=UserInterpretation(
                    judgement=AnswerJudgement.BACKCHANNEL,
                    dialogue_act=DialogueAct.BACKCHANNEL,
                ),
                turn_contract=TurnInterpretation(
                    call_id=self.state.call_id,
                    turn_id=self.turn_id,
                    raw_text=user_text,
                    state_version=self.state.state_version,
                    dialogue_act=DialogueAct.BACKCHANNEL,
                    judgement=AnswerJudgement.BACKCHANNEL,
                ),
                proposal=proposal,
                validated=validated,
                safety=self.safety.model_copy(deep=True),
            )

        next_turn = self.turn_id + 1
        if interp is None:
            interp, contract = self.interpreter.interpret(self.state, user_text, next_turn)
        elif contract is None:
            from packages.dialogue.interpretation import to_turn_interpretation

            contract = to_turn_interpretation(
                self.state,
                next_turn,
                user_text,
                interp,
                state_version=self.state.state_version,
            )

        return self._apply_user_turn(user_text, next_turn, interp, contract)

    def _apply_user_turn(
        self,
        user_text: str,
        next_turn: int,
        interp: UserInterpretation,
        contract: TurnInterpretation,
    ) -> SessionTurnResult:
        allow_new = not (
            self.state.risk_handling and self.state.fsm_state == FsmState.CONFIRM_SITUATION
        )
        SafetyEngine.ingest_transcript(self.safety, user_text, allow_new_episodes=allow_new)

        if interp.risk_false_alarm and self.state.risk_episode_id:
            SafetyEngine.resolve_false_alarm(self.safety, episode_id=self.state.risk_episode_id)

        risk_obs_id: str | None = None
        if (
            self.safety.active_risk == RiskLevel.RED
            and not self.state.risk_handling
            and self.state.fsm_state not in _RED_INTERRUPT_STATES
        ):
            CallFsm.interrupt_red(
                self.state,
                source_quote=user_text.strip(),
                episode_id=self.safety.active_episode_id,
            )
            self._append_event(
                "RED_SIGNAL",
                {"quote": user_text.strip(), "turn_id": next_turn},
            )
            risk_obs_id, ok, err = self._persist_risk(next_turn, user_text.strip())
            if not ok:
                return self._failed_turn(user_text, interp, contract, err or "risk persist")

        self.turn_id = next_turn
        gen = self._next_generation_id()
        proposal = Planner.plan_after_user(
            self.state, user_text, gen, self.turn_id, interp=interp
        )
        validated = Validator.validate(proposal)

        obs_ids, ok, err = self._persist_new_facts(self.turn_id)
        if risk_obs_id:
            obs_ids.append(risk_obs_id)
        if not ok:
            return self._failed_turn(
                user_text, interp, contract, err or "fact persist", proposal, validated
            )

        fin_ok, fin_err = self._finalize_call_if_needed()
        return SessionTurnResult(
            user_text=user_text,
            interpretation=interp,
            turn_contract=contract,
            proposal=proposal,
            validated=validated,
            safety=self.safety.model_copy(deep=True),
            observation_ids=obs_ids,
            persist_ok=fin_ok,
            persist_error=fin_err,
        )

    def _failed_turn(
        self,
        user_text: str,
        interp: UserInterpretation,
        contract: TurnInterpretation,
        error: str,
        proposal: TurnProposal | None = None,
        validated: ValidatedTurn | None = None,
    ) -> SessionTurnResult:
        if proposal is None:
            proposal = Planner._terminal_noop(self.state, self.turn_id, self._next_generation_id())
        if validated is None:
            validated = Validator.validate(proposal)
        return SessionTurnResult(
            user_text=user_text,
            interpretation=interp,
            turn_contract=contract,
            proposal=proposal,
            validated=validated,
            safety=self.safety.model_copy(deep=True),
            persist_ok=False,
            persist_error=error,
        )

    def get_persisted_result(self) -> CallResultSnapshot | None:
        return self.store.get_call_result(self.state.call_id, self.state.family_id)

    def say(self, user_text: str) -> str:
        result = self.start() if self.turn_id == 0 else self.handle_user_text(user_text)
        if not result.validated.allowed:
            return ""
        return result.validated.speech
