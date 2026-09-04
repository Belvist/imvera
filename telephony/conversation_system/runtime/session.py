"""ConversationSession + TurnPipeline — RTC per-call lock."""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, List, Optional

from conversation_system.agenda.manager import AgendaManager
from conversation_system.domain.api import (
    CallSummary,
    TurnCommit,
    TurnPipelineError,
    TurnPlanV2,
)
from conversation_system.domain.fsm_types import (
    CallPhase,
    CallPhaseContext,
    FsmActionResult,
    FsmEvent,
)
from conversation_system.domain.understanding import MemoryPatch, TurnUnderstanding, ResponseGoal
from conversation_system.memory.state import ConversationMemory
from conversation_system.observer import Observer, ObserverPatch
from conversation_system.policy.fsm import CallPhaseMachine
from conversation_system.policy.llm_policy import gate_checkin_llm
from conversation_system.policy.resolver import IntentResolver
from conversation_system.reply.composer import ComposedReply, ReplyComposer
from conversation_system.safety.bridge import SafetyBridge
from conversation_system.turn.analyzer import TurnAnalyzer
from conversation_system.reply.pools import GREETING_POOL
from conversation_system.domain.turn_directive import TurnDirective
from conversation_system.variety.dedupe import DedupeGuard, VarietyEngine
from conversation_system.ledger.question_ledger import QuestionLedger, QuestionStatus
from conversation_system.ledger.segment_ledger import SegmentLedger
from conversation_system.ledger.fact_ledger import FactLedger
from conversation_system.ledger.event_log import EventLog, ConversationEventType
from conversation_system.ledger.action_supervisor import ActionSupervisor


_PROCESS_CRITICAL_PHASES = frozenset({
    CallPhase.RECORD_NOTIFY,
    CallPhase.CLOSING,
    CallPhase.SAFETY_CONFIRM,
    CallPhase.SAFETY_ACTIVE,
    CallPhase.TERMINAL,
    CallPhase.CRITICAL_PATH,
})


_log = logging.getLogger(__name__)


@dataclass
class ConversationSession:
    """One active call — owns memory, FSM, safety engine, lock."""

    call_id: str
    internal_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    memory: ConversationMemory = field(default_factory=ConversationMemory)
    agenda: AgendaManager = field(default_factory=AgendaManager.from_canonical)
    fsm: CallPhaseMachine = field(default_factory=CallPhaseMachine)
    safety: SafetyBridge = field(default_factory=SafetyBridge)
    variety: VarietyEngine = field(default_factory=VarietyEngine)
    composer: ReplyComposer = field(default_factory=ReplyComposer)
    resolver: IntentResolver = field(default_factory=IntentResolver)
    analyzer: TurnAnalyzer | None = None
    observer: Observer = field(default_factory=Observer)
    question_ledger: QuestionLedger = field(default_factory=QuestionLedger)
    segment_ledger: SegmentLedger = field(default_factory=SegmentLedger)
    fact_ledger: FactLedger = field(default_factory=FactLedger)
    event_log: EventLog = field(default_factory=EventLog)
    action_supervisor: ActionSupervisor = field(default_factory=ActionSupervisor)
    lock: threading.RLock = field(default_factory=threading.RLock)
    started: bool = False
    greeting_played: bool = False
    last_plan: TurnPlanV2 | None = None
    last_action: FsmActionResult | None = None
    last_understanding: TurnUnderstanding | None = None
    pending_spoken: str = ""

    def __post_init__(self) -> None:
        self.memory.call_id = self.call_id
        if self.analyzer is None:
            self.analyzer = TurnAnalyzer(safety_engine=self.safety.engine)
        if not isinstance(self.composer, ReplyComposer) \
                or self.composer.variety is not self.variety:
            self.composer = ReplyComposer(
                variety=self.variety,
                dedupe=DedupeGuard(self.variety),
            )

    def ctx(self, understanding: TurnUnderstanding | None = None) -> CallPhaseContext:
        return CallPhaseContext(
            memory=self.memory,
            agenda=self.agenda,
            understanding=understanding,
            safety=None,
            hour=datetime.now().hour,
            question_ledger=self.question_ledger,
        )


class TurnPipeline:
    """Single-turn processing under session lock."""

    SCENARIO_VERSION = "conversation_system_v2_observer_phase6"

    def begin(
        self,
        session: ConversationSession,
        *,
        caller_id: str = "",
        greeting_played: bool = False,
    ) -> str:
        with session.lock:
            session.memory.caller_id = caller_id
            session.started = True
            session.fsm.reset()
            greeting = session.variety.pick_from_pool(
                GREETING_POOL, pool_key="greeting")
            session.agenda.assign_greeting(greeting)
            session.variety.remember(greeting)
            session.pending_spoken = greeting
            session.greeting_played = greeting_played
            session.fsm.phase = (
                CallPhase.LISTEN if greeting_played else CallPhase.GREETING
            )
            if greeting_played:
                session.memory.last_question = greeting
            return greeting

    def plan_turn(
        self,
        session: ConversationSession,
        *,
        transcript: str = "",
        reason: str | None = None,
        stt_confidence: float | None = None,
    ) -> TurnPlanV2:
        with session.lock:
            try:
                return self._plan_turn_unlocked(
                    session,
                    transcript=transcript,
                    reason=reason,
                    stt_confidence=stt_confidence,
                )
            except Exception as exc:
                raise TurnPipelineError(str(exc)) from exc

    def _plan_turn_unlocked(
        self,
        session: ConversationSession,
        *,
        transcript: str,
        reason: str | None,
        stt_confidence: float | None,
    ) -> TurnPlanV2:
        analyzer = session.analyzer
        assert analyzer is not None

        if not session.greeting_played and session.fsm.phase == CallPhase.GREETING:
            session.greeting_played = True
            greeting = session.pending_spoken or session.agenda.greeting_text()
            plan = TurnPlanV2(
                user_text="",
                spoken_reply=greeting,
                stream=False,
                terminal=False,
                verdict="ok",
                safety_status="unknown",
                dialogue_step=session.memory.turn_no,
                greeting=greeting,
                meta=self._meta(session, goal_kind="greet"),
            )
            session.last_plan = plan
            return plan

        understanding = analyzer.analyze(
            transcript,
            reason=reason,
            confidence=stt_confidence,
            last_question=session.memory.last_question,
            current_topic=session.agenda.current_topic_key(),
            agenda_question_open=session.agenda.question_open,
            clearing_symptom=session.memory.flags.clearing_symptom,
        )
        session.last_understanding = understanding
        session.memory.last_input_reason = understanding.input_reason.value

        observer_patch = session.observer.observe_turn(
            session.memory,
            understanding,
            last_exchange=(
                understanding.clean_text or "",
                session.memory.last_reply or "",
            ),
        )
        for patch in observer_patch.memory_patches:
            session.memory.apply(patch)

        safety_result = session.safety.process(
            session.memory,
            understanding,
            phase=session.fsm.phase.value,
            stt_confidence=stt_confidence,
        )
        session.memory.safety_status = safety_result.safety_status

        resolver_out = session.resolver.resolve(
            session.memory,
            session.agenda,
            understanding,
            phase=session.fsm.phase,
            safety=safety_result.verdict,
            safety_events=safety_result.events,
            observer=observer_patch,
        )

        ctx = session.ctx(understanding)
        ctx.safety = safety_result.verdict
        action = self._dispatch_events(session, ctx, resolver_out.events)
        session.last_action = action

        for patch in action.patches:
            session.memory.apply(patch)
        session.agenda.sync_from_memory(
            cursor=session.memory.agenda_cursor,
            question_open=session.memory.agenda_question_open,
            done=session.memory.flags.agenda_done,
            paused=session.memory.flags.agenda_paused,
            deferred_topic=session.memory.deferred_topic,
            wellness_band=session.memory.wellness_band,
            record_notified=session.agenda.record_notified,
            on_good_path=session.agenda.on_good_path,
            on_bad_path=session.agenda.on_bad_path,
            good_probe_index=session.agenda.good_probe_index,
            bad_symptom_probe_index=session.agenda.bad_symptom_probe_index,
            covered_good_slots=session.agenda.covered_slots(),
            interruption_phase=session.agenda.interruption.return_phase,
            interruption_slot_index=session.agenda.interruption.return_slot_index,
            interruption_slot=session.agenda.interruption.return_slot,
            interruption_question_id=session.agenda.interruption.return_question_id,
        )

        goal = action.goal
        decision_goal = resolver_out.decision.primary_goal
        phase = session.fsm.phase
        if action.terminal or phase in _PROCESS_CRITICAL_PHASES:
            goal = action.goal
        elif action.goal.scripted_only and not action.goal.allow_llm:
            goal = action.goal
        elif action.goal.allow_llm and not action.goal.scripted_only:
            goal = action.goal
        elif decision_goal.scripted_only and not decision_goal.allow_llm:
            goal = decision_goal
        elif decision_goal.allow_llm and not decision_goal.scripted_only:
            goal = decision_goal

        allow_llm = bool(
            not action.terminal
            and not goal.scripted_only
            and (goal.allow_llm or resolver_out.decision.allow_llm)
        )
        if allow_llm and not goal.allow_llm:
            goal = ResponseGoal(
                kind=goal.kind,
                topic=goal.topic,
                symptom_focus=goal.symptom_focus,
                allow_llm=True,
                scripted_only=False,
                must_do=goal.must_do,
                forbidden=goal.forbidden,
                next_topic=goal.next_topic,
            )

        goal, allow_llm = gate_checkin_llm(goal, allow_llm)

        composed = session.composer.compose(
            goal,
            session.memory,
            session.agenda,
            allow_llm=allow_llm,
        )
        _log.info(
            "turn_plan call=%s goal=%s allow_llm=%s reply_source=%s probe_idx=%s",
            session.call_id,
            goal.kind.value,
            allow_llm,
            composed.source,
            session.agenda.bad_symptom_probe_index,
        )

        from conversation_system.domain.understanding import ResponseGoalKind
        current_slot = session.agenda.current_good_slot(session.question_ledger)
        if (
            goal.kind == ResponseGoalKind.ASK_TOPIC
            and current_slot
            and session.question_ledger.can_ask_slot(current_slot)
            and session.question_ledger.record_for_slot(current_slot) is None
        ):
            session.question_ledger.plan_slot(
                current_slot,
                turn=session.memory.turn_no + 1,
            )

        merged_intent = self._compose_intent(
            session,
            goal=goal,
            observer_patch=observer_patch,
        )

        notes = list(action.record_notes) + list(resolver_out.decision.record_notes)
        for fact in session.agenda.extract_fact_candidates(understanding):
            session.memory.apply(MemoryPatch(add_fact=fact))

        verdict = self._merge_verdict(
            action.verdict,
            safety_result.verdict_label,
        )

        current_slot = session.agenda.current_good_slot(session.question_ledger)
        forbidden = session.agenda.forbidden_slots(session.question_ledger)
        if current_slot and not session.question_ledger.can_ask_slot(current_slot):
            forbidden = tuple(dict.fromkeys((*forbidden, current_slot)))

        plan = TurnPlanV2(
            user_text=understanding.raw_text,
            spoken_reply=composed.text,
            stream=allow_llm,
            terminal=action.terminal,
            verdict=verdict,
            safety_status=action.safety_status or safety_result.safety_status,
            record_notes=notes,
            dialogue_step=session.memory.turn_no + 1,
            meta=self._meta(
                session,
                goal_kind=goal.kind.value,
                phase_after=session.fsm.phase.value,
                allow_llm=allow_llm,
                reply_source=composed.source,
                intent=merged_intent,
                next_directive=observer_patch.next_directive,
                current_slot=current_slot,
                covered_slots=session.agenda.covered_slots(),
                forbidden_slots=forbidden,
            ),
        )
        session.event_log.append(
            ConversationEventType.TURN_PLANNED,
            turn=session.memory.turn_no + 1,
            goal_kind=goal.kind.value,
            slot=current_slot,
        )
        session.pending_spoken = composed.text
        session.last_plan = plan
        return plan

    def _dispatch_events(
        self,
        session: ConversationSession,
        ctx: CallPhaseContext,
        events: tuple[FsmEvent, ...],
    ) -> FsmActionResult:
        if not events:
            return session.fsm.dispatch(ctx, FsmEvent.E_UNHANDLED)
        result: FsmActionResult | None = None
        for ev in events:
            result = session.fsm.dispatch(ctx, ev)
        assert result is not None
        return result

    def stream_reply(
        self,
        session: ConversationSession,
        plan: TurnPlanV2,
    ) -> Iterator[str]:
        if plan.spoken_reply:
            yield plan.spoken_reply
            return
        with session.lock:
            if session.last_action is None:
                yield plan.spoken_reply or ""
                return
            for seg in session.composer.stream_segments(
                session.last_action.goal,
                session.memory,
                session.agenda,
                allow_llm=plan.meta.get("allow_llm", False),
            ):
                yield seg

    def commit_turn(
        self,
        session: ConversationSession,
        plan: TurnPlanV2,
        spoken_text: str,
    ) -> TurnCommit:
        with session.lock:
            from conversation_system.domain.pending_question import (
                apply_pending_to_memory,
            )
            from conversation_system.domain.understanding import ResponseGoalKind

            patches_before = len(session.memory.notes)
            spoken = (spoken_text or plan.spoken_reply or "").strip()
            spoken = session.action_supervisor.sanitize(
                spoken,
                fallback=plan.spoken_reply or spoken,
            )
            question = spoken if "?" in spoken else ""
            session.memory.record_turn(
                user_text=plan.user_text,
                agent_reply=spoken,
                question=question,
            )
            turn_no = session.memory.turn_no
            slot = session.agenda.current_good_slot()
            if question and slot and session.question_ledger.can_ask_slot(slot):
                try:
                    rec = session.question_ledger.plan_slot(slot, turn=turn_no)
                except ValueError:
                    rec = session.question_ledger.record_for_slot(slot)
                if rec is not None:
                    session.question_ledger.mark_asked(
                        rec.id,
                        text=question,
                        turn=turn_no,
                    )
                    session.event_log.append(
                        ConversationEventType.QUESTION_ASKED,
                        turn=turn_no,
                        slot=slot,
                        question_id=rec.id,
                    )
            covered = session.agenda.consume_last_covered_slot()
            if covered and plan.user_text.strip():
                session.question_ledger.mark_answered(
                    covered,
                    answer=plan.user_text.strip(),
                    turn=turn_no,
                )
                session.event_log.append(
                    ConversationEventType.QUESTION_ANSWERED,
                    turn=turn_no,
                    slot=covered,
                )
            if question:
                apply_pending_to_memory(
                    session.memory,
                    question,
                    turn_no=session.memory.turn_no,
                )
                session.variety.remember_question(question)
            if session.last_action and session.last_action.goal.kind == (
                    ResponseGoalKind.ANSWER_SIDE):
                session.memory.mark_question_answered()
            if session.last_understanding and (
                    session.last_understanding.speech_act.value == "repair"):
                session.memory.next_directive = ""
                state = session.memory.observer_state
                if hasattr(state, "next_directive"):
                    state.next_directive = ""
            if session.fsm.phase == CallPhase.GREETING and session.greeting_played:
                session.fsm.phase = CallPhase.LISTEN
            session.agenda.sync_to_memory()
            patch = session.agenda.sync_to_memory()
            session.memory.apply(patch)
            return TurnCommit(
                spoken_text=spoken,
                memory_patches_applied=len(session.memory.notes) - patches_before,
                phase=session.fsm.phase.value,
                agenda_cursor=session.memory.agenda_cursor,
                topics_discussed=list(session.memory.topics_discussed),
            )

    def mark_segment_played(
        self,
        session: ConversationSession,
        *,
        generation_id: int,
        segment_id: str = "",
        slot: str = "",
    ) -> None:
        """ASKED → PLAYING → PLAYED → HEARD when playback confirms segment."""
        with session.lock:
            turn = session.memory.turn_no
            if segment_id:
                existing = session.segment_ledger.last_for_generation(generation_id)
                if existing is None:
                    existing = session.segment_ledger.register_generated(
                        generation_id=generation_id,
                        segment_path=segment_id,
                    )
                session.segment_ledger.mark_played(existing.id)
            qid = (
                session.agenda.interruption.return_question_id
                or session.question_ledger.active_question_id()
            )
            if qid:
                active = session.question_ledger.record_by_id(qid)
                if active is not None and active.status == QuestionStatus.ASKED:
                    session.question_ledger.mark_playing(qid)
                    session.question_ledger.mark_played(qid)
                session.question_ledger.mark_heard(qid, turn=turn)
                session.event_log.append(
                    ConversationEventType.QUESTION_HEARD,
                    turn=turn,
                    question_id=qid,
                    generation_id=generation_id,
                    segment_id=segment_id,
                )
                session.event_log.append(
                    ConversationEventType.SEGMENT_PLAYED,
                    turn=turn,
                    question_id=qid,
                    generation_id=generation_id,
                    segment_id=segment_id,
                )
                return
            target_slot = (slot or session.agenda.current_good_slot(
                session.question_ledger)).strip()
            if not target_slot:
                return
            rec = session.question_ledger.record_for_slot(target_slot)
            if rec is None:
                return
            if generation_id and rec.generation_id and rec.generation_id != generation_id:
                return
            if rec.status == QuestionStatus.ASKED:
                session.question_ledger.mark_playing(rec.id)
                session.question_ledger.mark_played(rec.id)
            session.question_ledger.mark_heard(rec.id, turn=turn)
            session.event_log.append(
                ConversationEventType.QUESTION_HEARD,
                turn=turn,
                slot=target_slot,
                question_id=rec.id,
                generation_id=generation_id,
                segment_id=segment_id,
            )
            session.event_log.append(
                ConversationEventType.SEGMENT_PLAYED,
                turn=turn,
                slot=target_slot,
                question_id=rec.id,
                generation_id=generation_id,
                segment_id=segment_id,
            )

    def on_generation_cancelled(
        self,
        session: ConversationSession,
        *,
        generation_id: int,
    ) -> None:
        """Barge-in before question heard → CANCELLED."""
        with session.lock:
            session.question_ledger.mark_cancelled(generation_id=generation_id)
            session.segment_ledger.mark_cancelled(generation_id=generation_id)
            session.event_log.append(
                ConversationEventType.QUESTION_CANCELLED,
                turn=session.memory.turn_no,
                generation_id=generation_id,
            )
            session.event_log.append(
                ConversationEventType.BARGE_IN,
                turn=session.memory.turn_no,
                generation_id=generation_id,
            )

    def end_call(self, session: ConversationSession) -> CallSummary:
        with session.lock:
            verdict = session.memory.safety_status or "ok"
            if session.last_action and session.last_action.verdict:
                verdict = self._merge_verdict(
                    session.last_action.verdict,
                    session.memory.safety_status or "",
                )
            elif session.memory.safety_status:
                verdict = self._merge_verdict(
                    verdict, session.memory.safety_status)
            wb = (session.memory.wellness_band or "").strip().lower()
            if wb in ("bad", "medium"):
                verdict = self._merge_verdict(verdict, "attention")
            elif wb == "critical":
                verdict = self._merge_verdict(verdict, "alert")
            return CallSummary(
                verdict=verdict,
                notes=list(session.memory.notes),
                family_questions=[
                    {
                        "id": fq.id,
                        "text": fq.text,
                        "status": fq.status,
                        "answer": fq.answer,
                    }
                    for fq in session.memory.family_questions
                ],
                duration_turns=session.memory.turn_no,
            )

    def _merge_verdict(self, action_verdict: str, safety_label: str) -> str:
        """Prefer higher-severity label when FSM default is ok but safety escalated."""
        severity = {"ok": 0, "unknown": 0, "attention": 1, "alert": 2}
        av = (action_verdict or "ok").strip().lower()
        sv = (safety_label or "ok").strip().lower()
        if severity.get(sv, 0) > severity.get(av, 0):
            return sv
        return av or sv or "ok"

    def _meta(
        self,
        session: ConversationSession,
        *,
        goal_kind: str,
        phase_after: str | None = None,
        allow_llm: bool = False,
        reply_source: str = "pool",
        intent: str = "",
        next_directive: str = "",
        current_slot: str = "",
        covered_slots: tuple[str, ...] = (),
        forbidden_slots: tuple[str, ...] = (),
    ) -> dict:
        return {
            "scenario_version": self.SCENARIO_VERSION,
            "phase": session.fsm.phase.value,
            "phase_after": phase_after or session.fsm.phase.value,
            "goal_kind": goal_kind,
            "allow_llm": allow_llm,
            "reply_source": reply_source,
            "intent": intent,
            "next_directive": next_directive,
            "current_slot": current_slot,
            "covered_slots": list(covered_slots),
            "forbidden_slots": list(forbidden_slots),
            "agenda_context": {
                "current_slot": current_slot,
                "covered_slots": list(covered_slots),
                "forbidden_slots": list(forbidden_slots),
            },
        }

    def _compose_intent(
        self,
        session: ConversationSession,
        *,
        goal: ResponseGoal,
        observer_patch: ObserverPatch,
    ) -> str:
        goal_must = goal.must_do or self._intent_for_goal(goal)
        current_slot = session.agenda.current_good_slot(session.question_ledger)
        forbidden = session.agenda.forbidden_slots(session.question_ledger)
        pending_q = ""
        if session.memory.pending_question is not None:
            pending_q = session.memory.pending_question.prompt or ""
        directive = TurnDirective.from_parts(
            observer_handling=observer_patch.next_directive,
            goal_must_do=goal_must,
            required_slot=current_slot or goal.topic,
            required_action=goal_must,
            current_slot=current_slot,
            covered_slots=session.agenda.covered_slots(),
            forbidden_slots=forbidden,
            facts=tuple(session.memory.facts[-4:]),
            pending_question=pending_q,
            tone_policy="тёплый тон, 0–1 вопрос если уместен",
        )
        return directive.format()

    def _intent_for_goal(self, goal: ResponseGoal) -> str:
        if goal.must_do:
            return goal.must_do
        if goal.kind.value == "answer_side":
            return "Ответь на вопрос абонента коротко и по существу."
        if goal.kind.value == "repair":
            return "Повтори свою последнюю фразу чуть иначе."
        if goal.kind.value == "symptom_followup" and goal.symptom_focus:
            return f"Уточни про {goal.symptom_focus} одним вопросом."
        if goal.topic == "narrative":
            return "Откликнись на рассказ и задай один вопрос."
        return ""
