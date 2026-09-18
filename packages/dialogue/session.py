"""Unified call session — single entry for user events and policy ordering."""

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from packages.contracts.core import CallRecordStore, CallResultSnapshot
from packages.contracts.enums import AnswerJudgement, AsrQuality, DialogueAct, FsmState, RiskLevel
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
from packages.dialogue.transition_store import DialogueTransitionStore
from packages.dialogue.validator import Validator
from packages.dialogue_engine.effects import EndCallEffect, SpeakEffect, TimerEffect
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.mission import (
    CallMission,
    CustomMissionRequiresDialogueEngine,
    daily_check_mission,
)
from packages.dialogue_engine.runtime import dialogue_engine_active, log_runtime_truth
from packages.safety import SafetyEngine

_log = logging.getLogger("dialogue.session")
_session_runtime_logged = False

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
    from_engine: bool = False
    followup_speak_effects: list = Field(default_factory=list)
    speak_effect: SpeakEffect | None = None
    timer_effect: TimerEffect | None = None
    end_call_effect: EndCallEffect | None = None

    model_config = {"frozen": True}


class CallSession:
    def __init__(
        self,
        call_id: str,
        elder_display_name: str = "Анной Петровной",
        family_id: str = "",
        store: CallRecordStore | None = None,
        interpreter: Interpreter | None = None,
        mission: CallMission | None = None,
        mission_understanding_provider: object | None = None,
    ) -> None:
        if not family_id:
            raise ValueError("family_id is required for product calls")
        resolved_mission = mission if mission is not None else daily_check_mission()
        # H: custom mission must never silently fall back to legacy Planner.
        if resolved_mission.is_custom and not dialogue_engine_active():
            raise CustomMissionRequiresDialogueEngine(
                "Custom CallMission requires DialogueEngine "
                "(IMVERA_DIALOGUE_ENGINE + direct wellness opening). "
                "Refusing silent legacy Planner fallback."
            )
        self.mission = resolved_mission
        self.mission_understanding_provider = mission_understanding_provider
        self.state = DialogueState(
            call_id=call_id,
            elder_display_name=elder_display_name,
            family_id=family_id,
        )
        self.safety = SafetySnapshot()
        self.store = store or create_call_record_store()
        self.transitions = DialogueTransitionStore(self.store, family_id)
        self.interpreter = interpreter or Interpreter()
        self.turn_id = 0
        self._generation_seq = 0
        self._obs_seq = 0
        self._event_seq = 0
        self._persisted_obs_ids: list[str] = []
        self._persisted_keys: set[str] = set()
        self._engine: DialogueEngine | None = None
        self._playout_meta: dict[str, tuple[int, str]] = {}
        self._playout_effect_meta: dict[str, str] = {}
        self._deferred_engine_turn: SessionTurnResult | None = None
        self._engine_playout_followup: SessionTurnResult | None = None
        self._completed_playout_ids: set[str] = set()
        global _session_runtime_logged
        if not _session_runtime_logged:
            log_runtime_truth(_log)
            _session_runtime_logged = True
        if dialogue_engine_active():
            prior: dict[str, str] = {}
            if hasattr(self.store, "get_latest_family_snapshot"):
                snap = self.store.get_latest_family_snapshot(
                    family_id,
                    exclude_call_id=call_id,
                    elder_display_name=elder_display_name,
                )
                if snap is not None:
                    prior.update(snap.facts)
                    prior.update(
                        {k: str(v) for k, v in snap.metadata.items() if isinstance(v, str)}
                    )
            self._engine = DialogueEngine(
                call_id=call_id,
                elder_display_name=elder_display_name,
                # Stable per-client key for phrase memory (empty = disabled).
                client_id=f"{family_id}:{elder_display_name}",
                prior_call_context=prior,
                mission=resolved_mission,
                mission_understanding_provider=mission_understanding_provider,
            )
            _log.info(
                "DialogueEngine.on_session call_id=%s mode=single_writer mission=%s",
                call_id,
                resolved_mission.mission_id,
            )
        elif resolved_mission.is_custom:
            # Defense in depth — should already have raised above.
            raise CustomMissionRequiresDialogueEngine(
                "Custom CallMission constructed without DialogueEngine"
            )

    def uses_dialogue_engine(self) -> bool:
        return self._engine is not None

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

    def _persist_action_policy_shadow_records(self) -> None:
        """Persist shadow telemetry via CallEvent with bounded fail-open retry.

        Failures never abort the call. Failed records are requeued (max 64).
        Dropped records mark telemetry_health=degraded (not cutover evidence).
        """
        if self._engine is None:
            return
        try:
            from packages.dialogue_engine.action_policy_shadow_buffer import (
                drain_shadow_records,
                mark_shadow_persisted,
                requeue_shadow_records,
            )

            records = drain_shadow_records(self._engine.state)
        except Exception:
            _log.exception(
                "ACTION_POLICY_SHADOW drain failed call_id=%s", self.state.call_id
            )
            return
        failed: list[dict] = []
        for record in records:
            try:
                key = str(
                    record.get("idempotency_key")
                    or f"{self.state.call_id}:ACTION_POLICY_SHADOW:{self._event_seq + 1}"
                )
                ok = self._append_event(
                    "ACTION_POLICY_SHADOW",
                    record,
                    idempotency_key=key,
                )
                if ok:
                    mark_shadow_persisted(self._engine.state, 1)
                else:
                    failed.append(record)
                    _log.warning(
                        "ACTION_POLICY_SHADOW persist soft-fail call_id=%s key=%s",
                        self.state.call_id,
                        key,
                    )
            except Exception:
                failed.append(record)
                _log.exception(
                    "ACTION_POLICY_SHADOW persist exception call_id=%s",
                    self.state.call_id,
                )
        if failed:
            try:
                requeue_shadow_records(self._engine.state, failed)
            except Exception:
                _log.exception(
                    "ACTION_POLICY_SHADOW requeue failed call_id=%s",
                    self.state.call_id,
                )

    def _persist_action_policy_shadow_health(self) -> None:
        """Emit one ACTION_POLICY_SHADOW_HEALTH summary at call finalization."""
        if self._engine is None:
            return
        try:
            from packages.dialogue_engine.action_policy_shadow_buffer import (
                compute_telemetry_health_status,
            )

            payload = compute_telemetry_health_status(self._engine.state)
            self._append_event(
                "ACTION_POLICY_SHADOW_HEALTH",
                payload,
                idempotency_key=f"{self.state.call_id}:ACTION_POLICY_SHADOW_HEALTH",
            )
        except Exception:
            _log.exception(
                "ACTION_POLICY_SHADOW_HEALTH persist failed call_id=%s",
                self.state.call_id,
            )

    def _snapshot(self) -> CallResultSnapshot:
        facts = {k: v.value for k, v in self.state.facts.items()}
        quotes = {k: v.source_quote for k, v in self.state.facts.items()}
        existing = self.store.get_call_result(self.state.call_id, self.state.family_id)
        metadata = dict(existing.metadata) if existing else {}
        from packages.dialogue.transition_store import _load_outbox, _state_to_metadata
        from packages.dialogue_engine.check_path import build_call_metadata
        from packages.dialogue_engine.mission_result import (
            build_call_outcomes,
            build_mission_result,
        )

        outbox = _load_outbox(metadata)
        metadata.update(_state_to_metadata(self.state, None, outbox))
        # Scope prior-call context to the person, not the family: another
        # подопечный must never inherit these facts (reviewer item 3).
        metadata["elder_display_name"] = self.state.elder_display_name
        mission_result = None
        outcomes = None
        if self._engine is not None:
            metadata.update(build_call_metadata(self._engine.state))
            mission_result = build_mission_result(self._engine.state)
            outcomes = build_call_outcomes(
                self._engine.state,
                mission_result=mission_result,
                legacy_public_status=(
                    self.state.public_status.value
                    if getattr(self.state, "public_status", None)
                    else None
                ),
            )
            metadata["mission_result"] = mission_result.model_dump(mode="json")
            metadata["outcomes"] = outcomes.model_dump(mode="json")
            # Project custom goal answers into facts for older readers (non-authoritative).
            for g in mission_result.goals:
                if g.value is not None:
                    facts[g.goal_id] = g.value
                    if g.evidence:
                        quotes[g.goal_id] = g.evidence[0]
        return CallResultSnapshot(
            call_id=self.state.call_id,
            family_id=self.state.family_id,
            fsm_state=self.state.fsm_state,
            facts=facts,
            fact_quotes=quotes,
            observations=list(self._persisted_obs_ids),
            partial=bool(self.state.mandatory_remaining())
            if self._engine is None or self.mission.is_daily_check
            else (mission_result.status != "COMPLETED" if mission_result else True),
            call_ended=self.state.call_finalized,
            termination_reason=self.state.termination_reason,
            metadata=metadata,
            mission_result=mission_result,
            outcomes=outcomes,
        )

    def _finalize_call_if_needed(self) -> tuple[bool, str | None]:
        if not self.state.final_action_done or self.state.call_finalized:
            return True, None
        # Final flush attempt for any requeued shadow telemetry.
        self._persist_action_policy_shadow_records()
        self._persist_action_policy_shadow_health()
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

    def _build_engine_turn_result(
        self,
        user_text: str,
        interp: UserInterpretation,
        contract: TurnInterpretation,
        *,
        observation_ids: list[str] = (),
        persist_ok: bool = True,
        persist_error: str | None = None,
    ) -> SessionTurnResult:
        assert self._engine is not None
        speak = self._engine.pop_speak_effect()
        timer = self._engine.pop_timer_effect() if speak is None else None
        hangup = (
            self._engine.pop_hangup_effect()
            if speak is None and timer is None
            else None
        )
        if speak is None and timer is not None:
            self._engine.sync_to_legacy(self.state)
            slot = self.state.waiting_on_goal or self.state.pending_slot
            goal = self.state.get_goal(slot) if slot else None
            gen = self._next_generation_id()
            proposal = TurnProposal(
                turn_id=self.turn_id,
                generation_id=gen,
                speech="",
                intent="wait_for_continuation",
                fsm_state=self.state.fsm_state,
                mandatory_remaining=self.state.mandatory_remaining(),
                wait_goal_id=goal.goal_id if goal else None,
            )
            validated = Validator.validate(proposal)
            commit = self.transitions.commit_transition(self.state, proposal)
            return SessionTurnResult(
                user_text=user_text,
                interpretation=interp,
                turn_contract=contract,
                proposal=proposal,
                validated=validated,
                safety=self.safety.model_copy(deep=True),
                observation_ids=list(observation_ids),
                persist_ok=persist_ok and commit.ok,
                persist_error=persist_error or commit.error,
                from_engine=True,
                timer_effect=timer,
            )
        if speak is None and hangup is not None:
            gen = self._next_generation_id()
            proposal = TurnProposal(
                turn_id=self.turn_id,
                generation_id=gen,
                speech="",
                intent="end_call",
                fsm_state=self.state.fsm_state,
                mandatory_remaining=self.state.mandatory_remaining(),
            )
            validated = Validator.validate(proposal)
            return SessionTurnResult(
                user_text=user_text,
                interpretation=interp,
                turn_contract=contract,
                proposal=proposal,
                validated=validated,
                safety=self.safety.model_copy(deep=True),
                observation_ids=list(observation_ids),
                persist_ok=persist_ok,
                persist_error=persist_error,
                from_engine=True,
                end_call_effect=hangup,
            )
        if speak is None:
            gen = self._next_generation_id()
            # Engine-only fallback: identical to Planner._terminal_noop but
            # without the legacy Planner dependency (pure construction from
            # already-synced values; Validator semantics unchanged).
            proposal = TurnProposal(
                turn_id=self.turn_id,
                generation_id=gen,
                speech="",
                intent="terminal_noop",
                fsm_state=self.state.fsm_state,
                mandatory_remaining=self.state.mandatory_remaining(),
            )
            validated = Validator.validate(proposal)
            return SessionTurnResult(
                user_text=user_text,
                interpretation=interp,
                turn_contract=contract,
                proposal=proposal,
                validated=validated,
                safety=self.safety.model_copy(deep=True),
                observation_ids=list(observation_ids),
                persist_ok=persist_ok,
                persist_error=persist_error,
                from_engine=True,
            )
        followups = self._engine.drain_speak_effects()
        self._engine.sync_to_legacy(self.state)
        self._playout_meta[speak.generation_id] = (speak.generation, speak.question_id)
        self._playout_effect_meta[speak.generation_id] = speak.effect_id
        for fx in followups:
            self._playout_meta[fx.generation_id] = (fx.generation, fx.question_id)
            self._playout_effect_meta[fx.generation_id] = fx.effect_id
        proposal = self._engine.effect_to_proposal(speak, self.turn_id, self.state)
        validated = Validator.validate(proposal)
        commit = self.transitions.commit_transition(self.state, proposal)
        return SessionTurnResult(
            user_text=user_text,
            interpretation=interp,
            turn_contract=contract,
            proposal=proposal,
            validated=validated,
            safety=self.safety.model_copy(deep=True),
            observation_ids=list(observation_ids),
            persist_ok=persist_ok and commit.ok,
            persist_error=persist_error or commit.error,
            from_engine=True,
            followup_speak_effects=followups,
            speak_effect=speak,
        )

    def handle_effect_failed(self, effect_id: str, *, stage: str, error: str = "") -> None:
        if self._engine is None:
            return
        self._engine.on_effect_failed(effect_id, stage=stage, error=error)
        self._engine.sync_to_legacy(self.state)

    def defer_engine_turn(self, result: SessionTurnResult) -> None:
        if self._engine is None or result.speak_effect is None:
            return
        self._deferred_engine_turn = result
        self._engine.on_delivery_deferred(result.speak_effect)

    def is_engine_speak_valid(self, effect: SpeakEffect) -> bool:
        if self._engine is None:
            return True
        return self._engine.is_speak_effect_valid(effect)

    def flush_deferred_engine_turn(self) -> SessionTurnResult | None:
        if self._engine is None or self._deferred_engine_turn is None:
            return None
        result = self._deferred_engine_turn
        effect = result.speak_effect
        if effect is not None and not self._engine.is_speak_effect_valid(effect):
            self._deferred_engine_turn = None
            return self.handle_stale_speak_effect(effect)
        self._deferred_engine_turn = None
        self._engine.clear_deferred_speak()
        return result

    def handle_stale_speak_effect(self, effect: SpeakEffect) -> SessionTurnResult | None:
        if self._engine is None:
            return None
        self._engine.on_speak_effect_stale(effect)
        if (
            self._deferred_engine_turn is not None
            and self._deferred_engine_turn.speak_effect is not None
            and self._deferred_engine_turn.speak_effect.effect_id == effect.effect_id
        ):
            self._deferred_engine_turn = None
        return self._build_engine_followup_result()

    def _build_engine_followup_result(self) -> SessionTurnResult | None:
        if self._engine is None:
            return None
        contract = TurnInterpretation(
            call_id=self.state.call_id,
            turn_id=self.turn_id,
            raw_text="",
            dialogue_act=DialogueAct.UNCLEAR,
            judgement=AnswerJudgement.NO_ANSWER,
            state_version=self.state.state_version,
        )
        interp = UserInterpretation(
            judgement=AnswerJudgement.NO_ANSWER,
            dialogue_act=DialogueAct.UNCLEAR,
        )
        result = self._build_engine_turn_result(
            "",
            interp,
            contract,
            persist_ok=True,
        )
        if (
            result.speak_effect is None
            and result.timer_effect is None
            and result.end_call_effect is None
        ):
            return None
        return result

    def pop_engine_playout_followup(self) -> SessionTurnResult | None:
        followup = self._engine_playout_followup
        self._engine_playout_followup = None
        return followup

    def cancel_playout_action(self, generation_id: str) -> None:
        if self._engine is not None:
            effect_id = self._playout_effect_meta.pop(generation_id, None)
            if effect_id:
                self._engine.outbox.mark_cancelled(effect_id, reason="barge_in")
            meta = self._playout_meta.pop(generation_id, None)
            if meta:
                self._engine.on_playout_cancelled(meta[0], meta[1])
                self._engine.sync_to_legacy(self.state)
            return
        Planner.release_question_attempt(self.state, generation_id)

    def start(self) -> SessionTurnResult:
        ensure = self.store.ensure_call(self.state.call_id, self.state.family_id)
        self.turn_id += 1
        if self._engine is not None:
            self._engine.start()
            contract = TurnInterpretation(
                call_id=self.state.call_id,
                turn_id=self.turn_id,
                raw_text="",
                dialogue_act=DialogueAct.UNCLEAR,
                judgement=AnswerJudgement.NO_ANSWER,
                state_version=0,
            )
            interp = UserInterpretation(
                judgement=AnswerJudgement.NO_ANSWER,
                dialogue_act=DialogueAct.UNCLEAR,
            )
            self._append_event("CALL_STARTED", {"family_id": self.state.family_id})
            result = self._build_engine_turn_result(
                "",
                interp,
                contract,
                persist_ok=ensure.ok,
                persist_error=ensure.error,
            )
            self._append_event(
                "ENGINE_DECISION",
                {
                    "turn_id": self.turn_id,
                    "intent": result.proposal.intent,
                    "revision": self._engine.revision,
                },
                idempotency_key=f"{self.state.call_id}:engine:start",
            )
            self._persist_action_policy_shadow_records()
            return result
        gen = self._next_generation_id()
        proposal = Planner.plan_vera_turn(self.state, self.turn_id, gen)
        validated = Validator.validate(proposal)
        commit = self.transitions.commit_transition(self.state, proposal)
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
            persist_ok=ensure.ok and commit.ok,
            persist_error=ensure.error or commit.error,
        )

    def handle_user_text(
        self,
        user_text: str,
        *,
        interp: UserInterpretation | None = None,
        contract: TurnInterpretation | None = None,
        utterance_id: str | None = None,
        asr_quality: AsrQuality = AsrQuality.GOOD,
        rich_turn: object | None = None,
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

        return self._apply_user_turn(
            user_text,
            next_turn,
            interp,
            contract,
            utterance_id=utterance_id,
            asr_quality=asr_quality,
            rich_turn=rich_turn,
        )

    def _apply_user_turn(
        self,
        user_text: str,
        next_turn: int,
        interp: UserInterpretation,
        contract: TurnInterpretation,
        *,
        utterance_id: str | None = None,
        asr_quality: AsrQuality = AsrQuality.GOOD,
        rich_turn: object | None = None,
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
            if self._engine is not None:
                # DialogueEngine owns conversational safety when active.
                self._engine.on_safety_interrupt(
                    quote=user_text.strip(),
                    episode_id=self.safety.active_episode_id,
                    level="RED",
                )
                self._engine.sync_to_legacy(self.state)
                self._append_event(
                    "RED_SIGNAL",
                    {"quote": user_text.strip(), "turn_id": next_turn, "owner": "dialogue_engine"},
                )
                risk_obs_id, ok, err = self._persist_risk(next_turn, user_text.strip())
                if not ok:
                    return self._failed_turn(user_text, interp, contract, err or "risk persist")
                # Engine already produced SAFETY speech — do not also run mission turn.
                return self._build_engine_turn_result(
                    user_text,
                    interp,
                    contract,
                    observation_ids=[risk_obs_id] if risk_obs_id else [],
                )
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
        uid = utterance_id or f"u-{self.turn_id}"
        self.state.last_committed_utterance_id = uid
        self.state.first_user_turn_received = True
        if self._engine is not None:
            answer_slot = self._engine.answer_context_slot()
            if rich_turn is not None:
                self._engine.on_user_turn(uid, user_text, rich_turn=rich_turn)
                intent_label = getattr(rich_turn, "dialogue_act", "rich_turn")
            else:
                from packages.dialogue_engine.semantic import semantic_from_legacy

                semantic = semantic_from_legacy(
                    interp, text=user_text, answer_slot=answer_slot
                )
                self._engine.on_user_turn(uid, user_text, semantic)
                intent_label = semantic.act.value
            self._append_event(
                "ENGINE_DECISION",
                {
                    "turn_id": self.turn_id,
                    "utterance_id": uid,
                    "intent": intent_label,
                    "revision": self._engine.revision,
                    "answer_slot": answer_slot,
                    "skip_planner": True,
                    "rich_turn": rich_turn is not None,
                },
                idempotency_key=f"{self.state.call_id}:engine:{uid}",
            )
            self._persist_action_policy_shadow_records()
            _log.info(
                "ENGINE_DECISION call_id=%s turn=%s intent=%s rich_turn=%s "
                "skip_planner=true revision=%s",
                self.state.call_id,
                self.turn_id,
                intent_label,
                rich_turn is not None,
                self._engine.revision,
            )
            obs_ids, ok, err = self._persist_new_facts(self.turn_id)
            if risk_obs_id:
                obs_ids.append(risk_obs_id)
            if not ok:
                return self._failed_turn(
                    user_text, interp, contract, err or "fact persist"
                )
            fin_ok, fin_err = self._finalize_call_if_needed()
            return self._build_engine_turn_result(
                user_text,
                interp,
                contract,
                observation_ids=obs_ids,
                persist_ok=fin_ok,
                persist_error=fin_err,
            )
        gen = self._next_generation_id()
        proposal = Planner.plan_after_user(
            self.state,
            user_text,
            gen,
            self.turn_id,
            interp=interp,
            utterance_id=uid,
            asr_quality=asr_quality,
        )
        self._append_event(
            "PLANNER_DECISION",
            {
                "turn_id": self.turn_id,
                "utterance_id": uid,
                "intent": proposal.intent,
                "fsm_state": proposal.fsm_state.value,
                "state_version": self.state.state_version,
                "pending_slot": self.state.pending_slot,
                "user_act": interp.dialogue_act.value,
                "skip_planner": False,
            },
            idempotency_key=f"{self.state.call_id}:planner:{uid}",
        )
        _log.info(
            "PLANNER_DECISION call_id=%s turn=%s intent=%s skip_planner=false",
            self.state.call_id,
            self.turn_id,
            proposal.intent,
        )
        validated = Validator.validate(proposal)
        commit = self.transitions.commit_transition(self.state, proposal)

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
            persist_ok=fin_ok and commit.ok,
            persist_error=fin_err or commit.error,
        )

    def plan_identity_followup(self) -> SessionTurnResult:
        """Planner-only follow-up after identity intro TTS (no user turn)."""
        self.turn_id += 1
        gen = self._next_generation_id()
        proposal = Planner.plan_identity_question(self.state, self.turn_id, gen)
        validated = Validator.validate(proposal)
        commit = self.transitions.commit_transition(self.state, proposal)
        contract = TurnInterpretation(
            call_id=self.state.call_id,
            turn_id=self.turn_id,
            raw_text="",
            dialogue_act=DialogueAct.UNCLEAR,
            judgement=AnswerJudgement.NO_ANSWER,
            state_version=self.state.state_version,
        )
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
            persist_ok=commit.ok,
            persist_error=commit.error,
        )

    def handle_wait_expired(self, wait_id: str | None = None) -> SessionTurnResult:
        """Answer-wait timer — DialogueEngine when active, else legacy planner (tests only)."""
        self.turn_id += 1
        self._append_event(
            "WAIT_EXPIRED",
            {
                "turn_id": self.turn_id,
                "wait_id": wait_id,
                "pending_slot": self.state.pending_slot,
            },
            idempotency_key=f"{self.state.call_id}:wait-expired:{wait_id or self.turn_id}",
        )
        contract = TurnInterpretation(
            call_id=self.state.call_id,
            turn_id=self.turn_id,
            raw_text="",
            dialogue_act=DialogueAct.UNCLEAR,
            judgement=AnswerJudgement.NO_ANSWER,
            state_version=self.state.state_version,
        )
        interp = UserInterpretation(
            judgement=AnswerJudgement.NO_ANSWER,
            dialogue_act=DialogueAct.UNCLEAR,
        )
        if self._engine is not None:
            self._engine.on_timer_expired(wait_id or "")
            _log.info(
                "ENGINE_DECISION call_id=%s turn=%s event=timer_expired skip_planner=true",
                self.state.call_id,
                self.turn_id,
            )
            self._persist_action_policy_shadow_records()
            fin_ok, fin_err = self._finalize_call_if_needed()
            return self._build_engine_turn_result(
                "",
                interp,
                contract,
                persist_ok=fin_ok,
                persist_error=fin_err,
            )
        if dialogue_engine_active():
            raise RuntimeError(
                "handle_wait_expired: planner path blocked while DialogueEngine is active"
            )
        gen = self._next_generation_id()
        proposal = Planner.plan_wait_expired(self.state, self.turn_id, gen)
        validated = Validator.validate(proposal)
        commit = self.transitions.commit_transition(self.state, proposal)
        fin_ok, fin_err = self._finalize_call_if_needed()
        return SessionTurnResult(
            user_text="",
            interpretation=interp,
            turn_contract=contract,
            proposal=proposal,
            validated=validated,
            safety=self.safety.model_copy(deep=True),
            persist_ok=fin_ok and commit.ok,
            persist_error=fin_err or commit.error,
        )

    def mark_spoken_action(self, generation_id: str) -> bool:
        followup: SessionTurnResult | None = None
        if self._engine is not None:
            if generation_id in self._completed_playout_ids:
                return True
            effect_id = self._playout_effect_meta.get(generation_id)
            if effect_id:
                record = self._engine.outbox.get_record(effect_id)
                if record and record.status.value in {
                    "COMPLETED",
                    "CANCELLED",
                    "STALE",
                    "FAILED",
                }:
                    return True
            meta = self._playout_meta.pop(generation_id, None)
            if meta:
                if effect_id:
                    self._engine.outbox.mark_completed(effect_id)
                    self._playout_effect_meta.pop(generation_id, None)
                self._engine.on_playout_completed(meta[0], meta[1])
                self._completed_playout_ids.add(generation_id)
            followup = self._build_engine_followup_result()
            if followup is not None and (
                followup.speak_effect is not None
                or followup.timer_effect is not None
                or followup.end_call_effect is not None
            ):
                self._engine_playout_followup = followup
            self._engine.sync_to_legacy(self.state)
        result = self.transitions.mark_action_delivered(
            self.state,
            generation_id,
            skip_planner=self._engine is not None,
        )
        return result.ok

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

    def finalize_if_needed(self) -> tuple[bool, str | None]:
        if not self.state.final_action_done and not self.state.call_finalized:
            self.state.final_action_done = True
            if self.state.termination_reason is None:
                from packages.contracts.core import TerminationReason

                self.state.termination_reason = TerminationReason.DISCONNECTED
        return self._finalize_call_if_needed()

    def get_persisted_result(self) -> CallResultSnapshot | None:
        return self.store.get_call_result(self.state.call_id, self.state.family_id)

    def say(self, user_text: str) -> str:
        result = self.start() if self.turn_id == 0 else self.handle_user_text(user_text)
        if not result.validated.allowed:
            return ""
        return result.validated.speech
