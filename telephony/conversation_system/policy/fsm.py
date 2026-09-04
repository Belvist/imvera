"""CallPhaseMachine — declarative product-flow FSM."""
from __future__ import annotations

import logging
from typing import Callable, Iterable, List, Tuple

from conversation_system.agenda.topics import TOPIC_CLOSING, TOPIC_RECORD_NOTIFY, TOPIC_WELLNESS
from conversation_system.domain.fsm_types import (
    MAX_DISPATCH_DEPTH,
    CallPhase,
    CallPhaseContext,
    FsmActionResult,
    FsmEvent,
)
from conversation_system.domain.understanding import (
    MemoryPatch,
    ResponseGoal,
    ResponseGoalKind,
    SttReason,
)
from conversation_system.domain.wellness import WellnessBand, classify_wellness, good_path_probe_count
from conversation_system.reply.pools import BAD_SYMPTOM_PROBE_POOL
from core.fsm import StateMachine, UnhandledEvent

_log = logging.getLogger(__name__)

Guard = Callable[[CallPhaseContext, FsmEvent], bool]
Action = Callable[[CallPhaseContext, FsmEvent], FsmActionResult]


def _always(_ctx: CallPhaseContext, _ev: FsmEvent) -> bool:
    return True


def _empty_lt_5(ctx: CallPhaseContext, _ev: FsmEvent) -> bool:
    return ctx.memory.empty_turn_count < 5


def _probes_remain(ctx: CallPhaseContext, _ev: FsmEvent) -> bool:
    return ctx.probes_remain()


def _probes_done(ctx: CallPhaseContext, _ev: FsmEvent) -> bool:
    return not ctx.probes_remain()


def _resume_good_path(ctx: CallPhaseContext, _ev: FsmEvent) -> bool:
    if ctx.agenda.on_good_path:
        return True
    ret = (ctx.agenda.interruption.return_phase or "").strip()
    return ret == CallPhase.GOOD_PATH.value


def _resume_bad_path(ctx: CallPhaseContext, _ev: FsmEvent) -> bool:
    if ctx.agenda.on_bad_path:
        return True
    ret = (ctx.agenda.interruption.return_phase or "").strip()
    return ret == CallPhase.BAD_PATH.value


def _no_interrupt_resume(ctx: CallPhaseContext, _ev: FsmEvent) -> bool:
    """Side-answer speech with a saved interruption must not fall back to LISTEN."""
    return not (ctx.agenda.interruption.return_phase or "").strip()


class CallPhaseMachine:
    """Product FSM: GREETING → LISTEN → paths → RECORD_NOTIFY → CLOSING."""

    def __init__(self) -> None:
        self._sm = StateMachine("CallPhaseMachine", CallPhase.GREETING.value)
        self._build_transitions()

    @property
    def phase(self) -> CallPhase:
        return CallPhase(self._sm.state)

    @phase.setter
    def phase(self, value: CallPhase) -> None:
        self._sm.state = value.value

    def reset(self) -> None:
        self._sm.state = CallPhase.GREETING.value

    def all_phases(self) -> Tuple[CallPhase, ...]:
        return tuple(CallPhase)

    def all_events(self) -> Tuple[FsmEvent, ...]:
        return tuple(FsmEvent)

    def dispatch(
        self,
        ctx: CallPhaseContext,
        event: FsmEvent,
    ) -> FsmActionResult:
        """Run-to-completion dispatch with bounded re-dispatch depth."""
        ctx.dispatch_depth += 1
        try:
            if ctx.dispatch_depth > MAX_DISPATCH_DEPTH:
                return self._warm_ack(ctx, "dispatch_depth_exceeded")
            try:
                raw = self._sm.handle(ctx, event)
            except UnhandledEvent:
                raw = self._sm.handle(ctx, FsmEvent.E_UNHANDLED)
            result = self._coerce_result(raw, ctx)
            ctx.last_result = result
            if result.redispatch is not None:
                nested = self.dispatch(ctx, result.redispatch)
                patches = result.patches + nested.patches
                return FsmActionResult(
                    goal=nested.goal,
                    patches=patches,
                    terminal=nested.terminal or result.terminal,
                    verdict=nested.verdict or result.verdict,
                    safety_status=nested.safety_status or result.safety_status,
                    record_notes=result.record_notes + nested.record_notes,
                )
            return result
        finally:
            ctx.dispatch_depth -= 1

    def dispatch_totality(
        self,
        ctx: CallPhaseContext,
        event: FsmEvent,
    ) -> FsmActionResult:
        """Like dispatch but never raises — for totality tests."""
        try:
            return self.dispatch(ctx, event)
        except Exception as exc:
            _log.warning("fsm totality fallback: %s on %s", event, self.phase)
            return self._warm_ack(ctx, str(exc))

    def _coerce_result(
        self,
        raw: object,
        ctx: CallPhaseContext,
    ) -> FsmActionResult:
        if isinstance(raw, FsmActionResult):
            return raw
        return self._warm_ack(ctx, "missing_action_result")

    def _warm_ack(self, ctx: CallPhaseContext, note: str = "") -> FsmActionResult:
        patches = (MemoryPatch(append_note=f"fsm_fallback:{note}"),) if note else ()
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.ACKNOWLEDGE,
                scripted_only=True,
            ),
            patches=patches,
            verdict="ok",
        )

    def _build_transitions(self) -> None:
        sm = self._sm
        add = sm.add

        # --- Opening ---
        add(CallPhase.GREETING.value, FsmEvent.E_CALL_START.value,
            CallPhase.LISTEN.value, self._a_greeting_done, _always,
            "greeting->listen")
        add(CallPhase.GREETING.value, FsmEvent.E_SPEECH.value,
            CallPhase.LISTEN.value, self._a_greeting_done, _always,
            "greeting speech->listen")

        # --- Listen → branch ---
        add(CallPhase.LISTEN.value, FsmEvent.E_WELLNESS_GOOD.value,
            CallPhase.GOOD_PATH.value, self._a_enter_good_path, _always)
        add(CallPhase.LISTEN.value, FsmEvent.E_WELLNESS_BAD.value,
            CallPhase.BAD_PATH.value, self._a_enter_bad_path, _always)
        add(CallPhase.LISTEN.value, FsmEvent.E_WELLNESS_CRITICAL.value,
            CallPhase.CRITICAL_PATH.value, self._a_skip_to_notify, _always)
        add(CallPhase.LISTEN.value, FsmEvent.E_SPEECH.value,
            CallPhase.LISTEN.value, self._a_listen_ack, _always)
        add(CallPhase.LISTEN.value, FsmEvent.E_NARRATIVE.value,
            CallPhase.LISTEN.value, self._a_narrative_ack, _always)
        add(CallPhase.LISTEN.value, FsmEvent.E_SIDE_QUESTION.value,
            CallPhase.SIDE_ANSWER.value, self._a_side_enter, _always)
        add(CallPhase.LISTEN.value, FsmEvent.E_GREETING.value,
            CallPhase.LISTEN.value, self._a_hello_back, _always)
        add(CallPhase.CLARIFY.value, FsmEvent.E_GREETING.value,
            CallPhase.CLARIFY.value, self._a_hello_back, _always)

        # --- Good path ---
        add(CallPhase.GOOD_PATH.value, FsmEvent.E_PROBE_DONE.value,
            CallPhase.GOOD_PATH.value, self._a_ask_good_probe,
            _probes_remain)
        add(CallPhase.GOOD_PATH.value, FsmEvent.E_PROBE_DONE.value,
            CallPhase.RECORD_NOTIFY.value, self._a_record_notify,
            _probes_done, name="good_probe->notify")
        add(CallPhase.GOOD_PATH.value, FsmEvent.E_PROBES_COMPLETE.value,
            CallPhase.RECORD_NOTIFY.value, self._a_record_notify, _always)
        add(CallPhase.GOOD_PATH.value, FsmEvent.E_GREETING.value,
            CallPhase.GOOD_PATH.value, self._a_hello_back, _always)
        add(CallPhase.GOOD_PATH.value, FsmEvent.E_SPEECH.value,
            CallPhase.GOOD_PATH.value, self._a_path_ack, _always)
        add(CallPhase.GOOD_PATH.value, FsmEvent.E_SIDE_QUESTION.value,
            CallPhase.SIDE_ANSWER.value, self._a_side_enter, _always)
        add(CallPhase.GOOD_PATH.value, FsmEvent.E_NARRATIVE.value,
            CallPhase.GOOD_PATH.value, self._a_narrative_ack, _always)
        add(CallPhase.GOOD_PATH.value, FsmEvent.E_WELLNESS_BAD.value,
            CallPhase.BAD_PATH.value, self._a_enter_bad_path, _always)
        add(CallPhase.GOOD_PATH.value, FsmEvent.E_CORRECTION.value,
            CallPhase.BAD_PATH.value, self._a_correction_repath, _always)

        # --- Bad path ---
        add(CallPhase.BAD_PATH.value, FsmEvent.E_PROBE_DONE.value,
            CallPhase.BAD_PATH.value, self._a_ask_symptom_probe,
            _probes_remain)
        add(CallPhase.BAD_PATH.value, FsmEvent.E_PROBE_DONE.value,
            CallPhase.RECORD_NOTIFY.value, self._a_record_notify,
            _probes_done, name="bad_probe->notify")
        add(CallPhase.BAD_PATH.value, FsmEvent.E_PROBES_COMPLETE.value,
            CallPhase.RECORD_NOTIFY.value, self._a_record_notify, _always)
        add(CallPhase.BAD_PATH.value, FsmEvent.E_GREETING.value,
            CallPhase.BAD_PATH.value, self._a_hello_back, _always)
        add(CallPhase.BAD_PATH.value, FsmEvent.E_SPEECH.value,
            CallPhase.BAD_PATH.value, self._a_path_ack, _always)
        add(CallPhase.BAD_PATH.value, FsmEvent.E_SIDE_QUESTION.value,
            CallPhase.SIDE_ANSWER.value, self._a_side_enter, _always)
        add(CallPhase.BAD_PATH.value, FsmEvent.E_NARRATIVE.value,
            CallPhase.BAD_PATH.value, self._a_narrative_ack, _always)
        add(CallPhase.BAD_PATH.value, FsmEvent.E_CORRECTION.value,
            CallPhase.BAD_PATH.value, self._a_correction_ack, _always)

        # --- Critical fast path ---
        add(CallPhase.CRITICAL_PATH.value, FsmEvent.E_WELLNESS_CRITICAL.value,
            CallPhase.RECORD_NOTIFY.value, self._a_record_notify, _always)
        add(CallPhase.CRITICAL_PATH.value, FsmEvent.E_NOTIFY_DONE.value,
            CallPhase.CLOSING.value, self._a_critical_goodbye, _always)
        add(CallPhase.CRITICAL_PATH.value, FsmEvent.E_PROBES_COMPLETE.value,
            CallPhase.RECORD_NOTIFY.value, self._a_record_notify, _always)

        # --- Notify → close ---
        add(CallPhase.RECORD_NOTIFY.value, FsmEvent.E_NOTIFY_DONE.value,
            CallPhase.CLOSING.value, self._a_closing_by_band, _always)
        add(CallPhase.RECORD_NOTIFY.value, FsmEvent.E_SPEECH.value,
            CallPhase.CLOSING.value, self._a_closing_by_band, _always)

        # --- Closing ---
        add(CallPhase.CLOSING.value, FsmEvent.E_CLOSING_DIRECT.value,
            CallPhase.TERMINAL.value, self._a_terminal, _always)
        add(CallPhase.CLOSING.value, FsmEvent.E_CLOSING.value,
            CallPhase.TERMINAL.value, self._a_terminal, _always)
        add(CallPhase.CLOSING.value, FsmEvent.E_HANGUP.value,
            CallPhase.TERMINAL.value, self._a_terminal, _always)
        add(CallPhase.CLOSING.value, FsmEvent.E_SPEECH.value,
            CallPhase.TERMINAL.value, self._a_terminal, _always)

        # --- Clarify ladder ---
        add(CallPhase.CLARIFY.value, FsmEvent.E_EMPTY.value,
            CallPhase.CLARIFY.value, self._a_silence_ladder, _empty_lt_5)
        add(CallPhase.CLARIFY.value, FsmEvent.E_ECHO.value,
            CallPhase.CLARIFY.value, self._a_echo_ladder, _always)
        add(CallPhase.CLARIFY.value, FsmEvent.E_LOW_CONF.value,
            CallPhase.CLARIFY.value, self._a_silence_ladder, _always)
        add(CallPhase.CLARIFY.value, FsmEvent.E_WELLNESS_GOOD.value,
            CallPhase.GOOD_PATH.value, self._a_enter_good_path, _always)
        add(CallPhase.CLARIFY.value, FsmEvent.E_WELLNESS_BAD.value,
            CallPhase.BAD_PATH.value, self._a_enter_bad_path, _always)
        add(CallPhase.CLARIFY.value, FsmEvent.E_WELLNESS_CRITICAL.value,
            CallPhase.CRITICAL_PATH.value, self._a_skip_to_notify, _always)
        add(CallPhase.CLARIFY.value, FsmEvent.E_SPEECH.value,
            CallPhase.GOOD_PATH.value, self._a_resume_good_path,
            _resume_good_path, name="clarify->good_path")
        add(CallPhase.CLARIFY.value, FsmEvent.E_SPEECH.value,
            CallPhase.BAD_PATH.value, self._a_resume_bad_path,
            _resume_bad_path, name="clarify->bad_path")
        add(CallPhase.CLARIFY.value, FsmEvent.E_SPEECH.value,
            CallPhase.LISTEN.value, self._a_resume_listen, _always)

        # --- Side answer ---
        add(CallPhase.SIDE_ANSWER.value, FsmEvent.E_SPEECH.value,
            CallPhase.GOOD_PATH.value, self._a_side_resume,
            _resume_good_path, name="side_resume_good")
        add(CallPhase.SIDE_ANSWER.value, FsmEvent.E_SPEECH.value,
            CallPhase.BAD_PATH.value, self._a_side_resume,
            _resume_bad_path, name="side_resume_bad")
        add(CallPhase.SIDE_ANSWER.value, FsmEvent.E_SPEECH.value,
            CallPhase.LISTEN.value, self._a_side_resume, _no_interrupt_resume,
            name="side_resume_listen")
        add(CallPhase.SIDE_ANSWER.value, FsmEvent.E_SIDE_QUESTION.value,
            CallPhase.SIDE_ANSWER.value, self._a_side_enter, _always)
        add(CallPhase.SIDE_ANSWER.value, FsmEvent.E_PROBE_DONE.value,
            CallPhase.GOOD_PATH.value, self._a_resume_good_path,
            _resume_good_path, name="side->good")
        add(CallPhase.SIDE_ANSWER.value, FsmEvent.E_PROBE_DONE.value,
            CallPhase.BAD_PATH.value, self._a_resume_bad_path,
            _resume_bad_path, name="side->bad")

        # --- Safety ---
        add("*", FsmEvent.E_SAFETY_CONFIRMED.value,
            CallPhase.SAFETY_ACTIVE.value, self._a_safety_active, _always)
        add("*", FsmEvent.E_SAFETY_UNCERTAIN.value,
            CallPhase.SAFETY_CONFIRM.value, self._a_safety_confirm, _always)
        add("*", FsmEvent.E_SAFETY_POSSIBLE.value,
            CallPhase.SAFETY_CONFIRM.value, self._a_safety_confirm, _always)
        add(CallPhase.SAFETY_CONFIRM.value, FsmEvent.E_SAFETY_CLEARED.value,
            CallPhase.LISTEN.value, self._a_safety_cleared, _always)
        add(CallPhase.SAFETY_ACTIVE.value, FsmEvent.E_SAFETY_CLEARED.value,
            CallPhase.LISTEN.value, self._a_safety_cleared, _always)
        add(CallPhase.SAFETY_ACTIVE.value, FsmEvent.E_SPEECH.value,
            CallPhase.SAFETY_ACTIVE.value, self._a_safety_active, _always)

        # --- Global: user-initiated end / refusal ---
        add("*", FsmEvent.E_CLOSING_DIRECT.value,
            CallPhase.TERMINAL.value, self._a_user_initiated_close, _always)
        add("*", FsmEvent.E_CLOSING.value,
            CallPhase.TERMINAL.value, self._a_user_initiated_close, _always)
        add("*", FsmEvent.E_REFUSAL.value,
            CallPhase.TERMINAL.value, self._a_refusal_close, _always)

        # --- Global ---
        add("*", FsmEvent.E_REPAIR.value, "*",
            self._a_repair_repeat, _always)
        add("*", FsmEvent.E_ACK.value, "*",
            self._a_conv_ack, _always)
        add("*", FsmEvent.E_CORRECTION.value, "*",
            self._a_correction_ack, _always)
        add("*", FsmEvent.E_SIDE_QUESTION.value, CallPhase.SIDE_ANSWER.value,
            self._a_side_enter, _always, name="global_side_question")
        add("*", FsmEvent.E_NARRATIVE.value, "*",
            self._a_narrative_ack, _always)
        add("*", FsmEvent.E_HELP.value, "*",
            self._a_help_empathy, _always)
        add("*", FsmEvent.E_EMPTY.value, CallPhase.CLARIFY.value,
            self._a_enter_clarify, _always)
        add("*", FsmEvent.E_ECHO.value, CallPhase.CLARIFY.value,
            self._a_enter_clarify, _always)
        add("*", FsmEvent.E_LOW_CONF.value, CallPhase.CLARIFY.value,
            self._a_enter_clarify, _always)
        add("*", FsmEvent.E_UNHANDLED.value, "*",
            self._a_warm_ack, _always)

    # --- Actions (return ResponseGoal + MemoryPatch) ---

    def _a_greeting_done(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.GREET, scripted_only=True),
            patches=(ctx.agenda.sync_to_memory(),),
        )

    def _good_path_must_do(self, ctx: CallPhaseContext) -> str:
        return ctx.agenda.slot_must_do()

    def _a_enter_good_path(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        patches = []
        if ctx.understanding:
            patches.extend(ctx.agenda.mark_discussed(ctx.understanding))
        patches.append(ctx.agenda.apply_path_after_wellness(ctx.understanding))
        ctx.agenda.mark_question_asked()
        slot = ctx.agenda.current_good_slot()
        patches.append(ctx.agenda.sync_to_memory())
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.ASK_TOPIC,
                topic=slot or "проба хорошо",
                allow_llm=True,
                scripted_only=False,
                must_do=self._good_path_must_do(ctx),
                next_topic=slot or "проба хорошо",
            ),
            patches=tuple(patches),
        )

    def _a_enter_bad_path(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        patches = []
        if ctx.understanding:
            patches.extend(ctx.agenda.mark_discussed(ctx.understanding))
        patches.append(ctx.agenda.apply_path_after_wellness(ctx.understanding))
        focus = ""
        if ctx.understanding and ctx.understanding.symptom_focus:
            focus = ctx.understanding.symptom_focus
            patches.append(MemoryPatch(
                set_field={"active_symptom": focus},
                add_fact=f"жалоба: {focus}",
            ))
        ctx.agenda.mark_question_asked()
        patches.append(ctx.agenda.sync_to_memory())
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.SYMPTOM_FOLLOWUP,
                symptom_focus=focus,
                allow_llm=True,
                scripted_only=False,
                must_do=(
                    f"Уточни про {focus} одним вопросом."
                    if focus else "Уточни симптом одним вопросом."
                ),
            ),
            patches=tuple(patches),
        )

    def _a_skip_to_notify(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        patches = []
        if ctx.understanding:
            patches.extend(ctx.agenda.mark_discussed(ctx.understanding))
        patches.append(ctx.agenda.apply_path_after_wellness(ctx.understanding))
        critical = ctx.agenda.wellness_band == WellnessBand.CRITICAL
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.WRAP_UP, scripted_only=True),
            patches=tuple(patches),
            terminal=critical,
            verdict="alert" if critical else "ok",
            safety_status="alert" if critical else "ok",
        )

    def _a_ask_good_probe(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        patches = []
        if ctx.understanding:
            patches.extend(ctx.agenda.mark_discussed(ctx.understanding))
        ctx.agenda.mark_question_asked()
        patches.append(ctx.agenda.sync_to_memory())
        slot = ctx.agenda.current_good_slot()
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.ASK_TOPIC,
                topic=slot or "проба хорошо",
                allow_llm=True,
                scripted_only=False,
                must_do=self._good_path_must_do(ctx),
                next_topic=slot or "проба хорошо",
            ),
            patches=tuple(patches),
        )

    def _a_ask_symptom_probe(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        patches = []
        if ctx.understanding:
            patches.extend(ctx.agenda.mark_discussed(ctx.understanding))
        focus = ctx.memory.active_symptom or (
            ctx.understanding.symptom_focus if ctx.understanding else "")
        ctx.agenda.mark_question_asked()
        patches.append(ctx.agenda.sync_to_memory())
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.SYMPTOM_FOLLOWUP,
                symptom_focus=focus,
                allow_llm=True,
                scripted_only=False,
                must_do=(
                    f"Уточни про {focus} одним вопросом."
                    if focus else "Уточни симптом одним вопросом."
                ),
            ),
            patches=tuple(patches),
        )

    def _a_record_notify(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        patches: list[MemoryPatch] = []
        if ctx.understanding and ctx.agenda.semantic_close(ctx.understanding):
            patches.extend(ctx.agenda.mark_discussed(ctx.understanding))
        ctx.agenda._seek_topic(TOPIC_RECORD_NOTIFY)
        ctx.agenda.record_notified = True
        verdict = "ok"
        if ctx.agenda.on_bad_path and ctx.agenda.wellness_band in (
            WellnessBand.BAD,
            WellnessBand.MEDIUM,
        ):
            verdict = "attention"
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.WRAP_UP, scripted_only=True),
            patches=(
                *tuple(patches),
                MemoryPatch(
                    mark_topic_discussed=TOPIC_RECORD_NOTIFY,
                    append_note="записано для родных",
                ),
                MemoryPatch(set_field={"safety_status": verdict}),
                ctx.agenda.sync_to_memory(),
            ),
            verdict=verdict,
            safety_status=verdict,
            record_notes=("записано для родных",),
        )

    def _a_closing_by_band(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        ctx.agenda._seek_topic(TOPIC_CLOSING)
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.CLOSE, scripted_only=True),
            patches=(
                MemoryPatch(mark_topic_discussed=TOPIC_CLOSING),
                ctx.agenda.sync_to_memory(),
            ),
        )

    def _a_critical_goodbye(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        ctx.agenda.wellness_band = WellnessBand.CRITICAL
        ctx.agenda._seek_topic(TOPIC_CLOSING)
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.CLOSE, scripted_only=True),
            patches=(ctx.agenda.sync_to_memory(),),
            terminal=True,
            verdict="alert",
            safety_status="alert",
        )

    def _a_terminal(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.CLOSE, scripted_only=True),
            patches=(MemoryPatch(set_field={"flags": {"agenda_done": True}}),),
            terminal=True,
        )

    def _a_user_initiated_close(
        self,
        ctx: CallPhaseContext,
        _ev: FsmEvent,
    ) -> FsmActionResult:
        """Caller says goodbye mid-call — record for family and close."""
        patches: list[MemoryPatch] = []
        if not ctx.agenda.record_notified:
            ctx.agenda._seek_topic(TOPIC_RECORD_NOTIFY)
            ctx.agenda.record_notified = True
            patches.append(MemoryPatch(
                mark_topic_discussed=TOPIC_RECORD_NOTIFY,
                append_note="записано для родных",
            ))
        ctx.agenda._seek_topic(TOPIC_CLOSING)
        patches.append(MemoryPatch(mark_topic_discussed=TOPIC_CLOSING))
        patches.append(MemoryPatch(set_field={"flags": {"agenda_done": True}}))
        patches.append(ctx.agenda.sync_to_memory())
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.CLOSE, scripted_only=True),
            patches=tuple(patches),
            terminal=True,
            record_notes=("записано для родных",),
        )

    def _a_refusal_close(
        self,
        ctx: CallPhaseContext,
        _ev: FsmEvent,
    ) -> FsmActionResult:
        """Polite close when caller declines further questions."""
        if self.phase in (CallPhase.TERMINAL, CallPhase.CLOSING):
            return self._a_terminal(ctx, _ev)
        return self._a_user_initiated_close(ctx, _ev)

    def _a_listen_ack(self, ctx: CallPhaseContext, ev: FsmEvent) -> FsmActionResult:
        if ctx.understanding and ctx.understanding.clean_text:
            band = classify_wellness(ctx.understanding.clean_text)
            if band == WellnessBand.GOOD:
                return self._a_enter_good_path(ctx, FsmEvent.E_WELLNESS_GOOD)
            if band in (WellnessBand.BAD, WellnessBand.MEDIUM):
                return self._a_enter_bad_path(ctx, FsmEvent.E_WELLNESS_BAD)
            if band == WellnessBand.CRITICAL:
                return self._a_skip_to_notify(ctx, FsmEvent.E_WELLNESS_CRITICAL)
        ctx.agenda.mark_question_asked()
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.ASK_TOPIC,
                topic=TOPIC_WELLNESS,
                allow_llm=True,
                scripted_only=False,
                must_do="Мягко спроси как человек себя чувствует сегодня.",
                next_topic=TOPIC_WELLNESS,
            ),
            patches=(
                MemoryPatch(reset_empty_turns=True),
                ctx.agenda.sync_to_memory(),
            ),
        )

    def _a_path_ack(self, ctx: CallPhaseContext, ev: FsmEvent) -> FsmActionResult:
        if self.phase == CallPhase.GOOD_PATH:
            return self._a_good_path_continue(ctx, ev)
        if self.phase == CallPhase.BAD_PATH:
            return self._a_bad_path_continue(ctx, ev)
        return self._a_listen_ack(ctx, ev)

    def _a_good_path_continue(
        self, ctx: CallPhaseContext, ev: FsmEvent,
    ) -> FsmActionResult:
        """Speech on good path that did NOT close the probe — re-ask, no advance."""
        patches: tuple[MemoryPatch, ...] = (MemoryPatch(reset_empty_turns=True),)
        slot = ctx.agenda.current_good_slot()
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.ASK_TOPIC,
                topic=slot or "проба хорошо",
                allow_llm=True,
                scripted_only=False,
                must_do=self._good_path_must_do(ctx),
                next_topic=slot or "проба хорошо",
            ),
            patches=patches + (ctx.agenda.sync_to_memory(),),
        )

    def _a_bad_path_continue(
        self, ctx: CallPhaseContext, ev: FsmEvent,
    ) -> FsmActionResult:
        """Complaint / unclear speech on bad path — empathize, do NOT advance agenda."""
        patches: tuple[MemoryPatch, ...] = (MemoryPatch(reset_empty_turns=True),)
        focus = ctx.memory.active_symptom or (
            ctx.understanding.symptom_focus if ctx.understanding else "")
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.SYMPTOM_FOLLOWUP,
                symptom_focus=focus,
                allow_llm=False,
                scripted_only=True,
                must_do=(
                    "Человеку плохо. Сочувствуй коротко и спроси что именно "
                    "беспокоит — одним вопросом. Не благодари и не говори "
                    "«как приятно» / «рада»."
                ),
            ),
            patches=patches + (ctx.agenda.sync_to_memory(),),
        )

    def _a_narrative_ack(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        if not ctx.agenda.question_open:
            return self._a_listen_ack(ctx, _ev)
        patches = []
        if ctx.understanding and ctx.agenda.should_defer_for_narrative(ctx.understanding):
            patches.append(ctx.agenda.defer_current())
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.ACKNOWLEDGE,
                topic="narrative",
                allow_llm=True,
                scripted_only=False,
            ),
            patches=tuple(patches),
        )

    def _a_hello_back(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        if ctx.memory.flags.hello_back_done:
            # Repeated «алло»/«ало» while checking the line — confirm hearing,
            # repeat the last question; do NOT treat as wellness answer.
            return FsmActionResult(
                goal=ResponseGoal(
                    kind=ResponseGoalKind.REPAIR,
                    allow_llm=False,
                    scripted_only=True,
                    must_do=(
                        "Коротко подтверди что слышишь абонента "
                        "(«да, слышу вас»). Повтори свой последний вопрос "
                        "одной фразой. Не комментируй слово «алло»."
                    ),
                ),
            )
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.GREET, scripted_only=True),
            patches=(MemoryPatch(set_field={"flags": {"hello_back_done": True}}),),
        )

    def _a_side_enter(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        qid = ""
        ledger = getattr(ctx, "question_ledger", None)
        if ledger is not None and hasattr(ledger, "active_question_id"):
            qid = ledger.active_question_id() or ""
        # Action runs before dst change — self.phase is the pre-side state
        # (e.g. good_path). Nested side questions keep the original return phase.
        ret_phase = self.phase.value
        if ret_phase == CallPhase.SIDE_ANSWER.value:
            existing = (ctx.agenda.interruption.return_phase or "").strip()
            if existing:
                ret_phase = existing
        patch = ctx.agenda.defer_current(
            phase=ret_phase,
            return_question_id=qid,
        )
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.ANSWER_SIDE,
                allow_llm=True,
                scripted_only=False,
                must_do="Ответь на вопрос абонента коротко, без нового вопроса по повестке.",
            ),
            patches=(patch,),
        )

    def _a_correction_ack(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        focus = ctx.memory.active_symptom or (
            ctx.understanding.symptom_focus if ctx.understanding else "")
        patches = [MemoryPatch(append_note="correction_ack")]
        if ctx.understanding and ctx.understanding.symptom_focus:
            focus = ctx.understanding.symptom_focus
            patches.append(MemoryPatch(
                set_field={"active_symptom": focus},
                add_fact=f"исправление: {focus}",
            ))
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.SYMPTOM_FOLLOWUP,
                symptom_focus=focus,
                allow_llm=True,
                scripted_only=False,
            ),
            patches=tuple(patches),
        )

    def _a_correction_repath(self, ctx: CallPhaseContext, ev: FsmEvent) -> FsmActionResult:
        """Good path caller corrects/contradicts wellness — re-enter bad path."""
        ctx.agenda.on_good_path = False
        ctx.agenda.on_bad_path = True
        return self._a_correction_ack(ctx, ev)

    def _a_side_resume(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        patch = ctx.agenda.resume_after_interrupt()
        ret_phase = (ctx.agenda.interruption.return_phase or "").strip()
        if ret_phase == CallPhase.GOOD_PATH.value or ctx.agenda.on_good_path:
            ctx.agenda.on_good_path = True
            ctx.agenda.on_bad_path = False
            self.phase = CallPhase.GOOD_PATH
            slot = ctx.agenda.current_good_slot()
            ctx.agenda.clear_interruption()
            return FsmActionResult(
                goal=ResponseGoal(
                    kind=ResponseGoalKind.ASK_TOPIC,
                    topic=slot,
                    allow_llm=True,
                    scripted_only=False,
                    must_do=ctx.agenda.slot_must_do(slot),
                    forbidden=", ".join(ctx.agenda.forbidden_slots()),
                ),
                patches=(patch, ctx.agenda.sync_to_memory()),
            )
        if ret_phase == CallPhase.BAD_PATH.value or ctx.agenda.on_bad_path:
            self.phase = CallPhase.BAD_PATH
            focus = ctx.memory.active_symptom or (
                ctx.understanding.symptom_focus if ctx.understanding else "")
            ctx.agenda.clear_interruption()
            return FsmActionResult(
                goal=ResponseGoal(
                    kind=ResponseGoalKind.SYMPTOM_FOLLOWUP,
                    symptom_focus=focus,
                    allow_llm=True,
                    scripted_only=False,
                    must_do=(
                        f"Уточни про {focus} одним вопросом."
                        if focus else "Уточни симптом одним вопросом."
                    ),
                ),
                patches=(patch, ctx.agenda.sync_to_memory()),
            )
        ctx.agenda.clear_interruption()
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.ACKNOWLEDGE,
                allow_llm=True,
                scripted_only=False,
            ),
            patches=(patch, ctx.agenda.sync_to_memory()),
        )

    def _a_enter_clarify(self, ctx: CallPhaseContext, ev: FsmEvent) -> FsmActionResult:
        # First empty/low-conf/echo hop into CLARIFY — count once via patch only
        # (direct mutation here double-counted with MemoryPatch in _a_silence_ladder).
        # Background/TV bleed (OFF_AGENDA) must not escalate the silence ladder.
        patches: tuple[MemoryPatch, ...] = ()
        off_agenda = (
            ev == FsmEvent.E_ECHO
            and ctx.understanding is not None
            and ctx.understanding.input_reason == SttReason.OFF_AGENDA
        )
        if not off_agenda and ev in (
                FsmEvent.E_EMPTY, FsmEvent.E_LOW_CONF, FsmEvent.E_ECHO):
            patches = (MemoryPatch(increment_empty_turns=1),)
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.CLARIFY, scripted_only=True),
            patches=patches,
        )

    def _a_silence_ladder(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.CLARIFY, scripted_only=True),
            patches=(MemoryPatch(increment_empty_turns=1),),
        )

    def _a_echo_ladder(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        ctx.echo_turn_count += 1
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.CLARIFY, scripted_only=True),
        )

    def _a_resume_listen(self, ctx: CallPhaseContext, ev: FsmEvent) -> FsmActionResult:
        patches: tuple[MemoryPatch, ...] = (MemoryPatch(reset_empty_turns=True),)
        if ctx.understanding and ctx.understanding.clean_text:
            band = classify_wellness(ctx.understanding.clean_text)
            if band == WellnessBand.GOOD and not ctx.agenda.on_good_path:
                ctx.agenda.set_wellness_from_text(ctx.understanding.clean_text)
                patches = patches + (ctx.agenda.apply_path_after_wellness(ctx.understanding),)
                return self._a_ask_good_probe(ctx, ev)
            if band in (WellnessBand.BAD, WellnessBand.MEDIUM) and not ctx.agenda.on_bad_path:
                ctx.agenda.set_wellness_from_text(ctx.understanding.clean_text)
                patches = patches + (ctx.agenda.apply_path_after_wellness(ctx.understanding),)
                return self._a_ask_symptom_probe(ctx, ev)
            if band == WellnessBand.CRITICAL:
                ctx.agenda.set_wellness_from_text(ctx.understanding.clean_text)
                patches = patches + (ctx.agenda.apply_path_after_wellness(ctx.understanding),)
                return self._a_skip_to_notify(ctx, FsmEvent.E_WELLNESS_CRITICAL)
        if ctx.understanding and ctx.agenda.current_topic_key():
            discussed = ctx.agenda.mark_discussed(ctx.understanding)
            if discussed:
                patches = patches + tuple(discussed)
                if ctx.agenda.on_good_path:
                    return self._a_ask_good_probe(ctx, ev)
                if ctx.agenda.on_bad_path:
                    return self._a_ask_symptom_probe(ctx, ev)
        if ctx.agenda.question_open and ctx.memory.last_question:
            kind = ResponseGoalKind.ASK_TOPIC
            if ctx.agenda.on_bad_path:
                kind = ResponseGoalKind.SYMPTOM_FOLLOWUP
            return FsmActionResult(
                goal=ResponseGoal(
                    kind=kind,
                    allow_llm=True,
                    scripted_only=False,
                ),
                patches=patches,
            )
        return self._a_listen_ack(ctx, ev)

    def _a_resume_good_path(self, ctx: CallPhaseContext, ev: FsmEvent) -> FsmActionResult:
        patches: tuple[MemoryPatch, ...] = (MemoryPatch(reset_empty_turns=True),)
        if ctx.understanding and ctx.agenda.semantic_close(ctx.understanding):
            discussed = tuple(ctx.agenda.mark_discussed(ctx.understanding))
            patches = patches + discussed
            if not ctx.probes_remain():
                return self._a_record_notify(ctx, ev)
            return self._a_ask_good_probe(ctx, ev)
        ctx.agenda.mark_question_asked()
        slot = ctx.agenda.current_good_slot()
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.ASK_TOPIC,
                topic=slot or "проба хорошо",
                allow_llm=True,
                scripted_only=False,
                must_do=self._good_path_must_do(ctx),
                next_topic=slot or "проба хорошо",
            ),
            patches=patches + (ctx.agenda.sync_to_memory(),),
        )

    def _a_resume_bad_path(self, ctx: CallPhaseContext, ev: FsmEvent) -> FsmActionResult:
        patches: tuple[MemoryPatch, ...] = (MemoryPatch(reset_empty_turns=True),)
        if ctx.understanding and ctx.agenda.semantic_close(ctx.understanding):
            discussed = tuple(ctx.agenda.mark_discussed(ctx.understanding))
            patches = patches + discussed
            if not ctx.probes_remain():
                return self._a_record_notify(ctx, ev)
            return self._a_ask_symptom_probe(ctx, ev)
        focus = ctx.memory.active_symptom or (
            ctx.understanding.symptom_focus if ctx.understanding else "")
        ctx.agenda.mark_question_asked()
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.SYMPTOM_FOLLOWUP,
                symptom_focus=focus,
                allow_llm=True,
                scripted_only=False,
                must_do=(
                    f"Уточни про {focus} одним вопросом."
                    if focus else "Уточни симптом одним вопросом."
                ),
            ),
            patches=patches + (ctx.agenda.sync_to_memory(),),
        )

    def _a_safety_confirm(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        ctx.safety_confirm_pending = True
        notes = ()
        if ctx.safety and ctx.safety.notes:
            notes = tuple(str(n) for n in ctx.safety.notes)
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.SAFETY_CONFIRM, scripted_only=True),
            patches=(MemoryPatch(set_field={"safety_status": "attention"}),),
            verdict="attention",
            safety_status="attention",
            record_notes=notes,
        )

    def _a_safety_active(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        notes = ("тревога: подтверждено",)
        if ctx.safety and ctx.safety.notes:
            notes = notes + tuple(str(n) for n in ctx.safety.notes)
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.SAFETY_ACTIVE, scripted_only=True),
            patches=(MemoryPatch(set_field={"safety_status": "alert"}),),
            verdict="alert",
            safety_status="alert",
            record_notes=notes,
            terminal=True,
        )

    def _a_safety_cleared(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        ctx.safety_confirm_pending = False
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.ACKNOWLEDGE, scripted_only=True),
            patches=(MemoryPatch(set_field={"safety_status": "ok"}),),
            verdict="ok",
            safety_status="ok",
        )

    def _a_help_empathy(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        ctx.agenda.mark_question_asked()
        return FsmActionResult(
            goal=ResponseGoal(kind=ResponseGoalKind.HELP_OFFER, scripted_only=True),
            patches=(
                MemoryPatch(
                    append_note="запрос помощи",
                    add_fact="просит помощь",
                ),
                ctx.agenda.sync_to_memory(),
            ),
            verdict="attention",
            safety_status="attention",
        )

    def _a_repair_repeat(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.REPAIR,
                allow_llm=True,
                scripted_only=False,
                must_do="Повтори свой последний вопрос другими словами, без новой темы.",
            ),
        )

    def _a_conv_ack(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        return FsmActionResult(
            goal=ResponseGoal(
                kind=ResponseGoalKind.ACKNOWLEDGE,
                allow_llm=True,
                scripted_only=False,
                must_do="Мягко продолжи разговор одним вопросом о самочувствии. "
                "Не говори что услышала или записала — связь могла быть плохой.",
            ),
        )

    def _a_warm_ack(self, ctx: CallPhaseContext, _ev: FsmEvent) -> FsmActionResult:
        if ctx.agenda.on_bad_path and ctx.agenda.wellness_band in (
            WellnessBand.BAD,
            WellnessBand.MEDIUM,
        ):
            focus = ctx.memory.active_symptom or (
                ctx.understanding.symptom_focus if ctx.understanding else ""
            )
            ctx.agenda.mark_question_asked()
            return FsmActionResult(
                goal=ResponseGoal(
                    kind=ResponseGoalKind.SYMPTOM_FOLLOWUP,
                    symptom_focus=focus,
                    allow_llm=False,
                    scripted_only=True,
                    must_do=(
                        f"Уточни про {focus} одним вопросом."
                        if focus
                        else "Спроси что именно беспокоит — одним вопросом."
                    ),
                ),
                patches=(ctx.agenda.sync_to_memory(),),
                verdict="attention",
                safety_status="attention",
            )
        return self._warm_ack(ctx, f"unhandled:{_ev.value}")

    def transition_table(self) -> Iterable[str]:
        return (t.name for t in self._sm._transitions)
