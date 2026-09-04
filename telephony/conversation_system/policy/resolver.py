"""IntentResolver — maps understanding + safety to FSM events (no LLM)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from conversation_system.agenda.manager import AgendaManager
from conversation_system.domain.fsm_types import CallPhase, FsmEvent
from conversation_system.domain.pending_question import validate_pending_answer
from conversation_system.domain.understanding import (
    PolicyDecision,
    ResponseGoal,
    ResponseGoalKind,
    SpeechAct,
    SttReason,
    TurnUnderstanding,
)
from conversation_system.domain.wellness import (
    WellnessBand,
    bad_path_probe_count,
    classify_wellness,
)
from conversation_system.memory.state import ConversationMemory
from conversation_system.observer.observer import ObserverPatch
from conversation_system.turn._cleaners import short_real_answer, wellness_short_answer
from conversation_system.turn.analyzer import answers_wellness
from conversation_system.turn.dialogue_relevance import should_reject_mixed_capture
from core.safety_engine import VerdictEvent
from core.vocab import looks_like_garbage


@dataclass(frozen=True)
class ResolverOutput:
    """Events to feed FSM + optional pre-decision metadata."""

    events: tuple[FsmEvent, ...]
    decision: PolicyDecision


class IntentResolver:
    """Deterministic event selection — priority: safety > user Q > correction > repair > agenda."""

    def resolve(
        self,
        memory: ConversationMemory,
        agenda: AgendaManager,
        understanding: TurnUnderstanding,
        *,
        phase: CallPhase,
        safety: VerdictEvent | None = None,
        safety_events: Sequence[FsmEvent] = (),
        observer: ObserverPatch | None = None,
    ) -> ResolverOutput:
        conv_events = self._conversational_events(
            memory,
            agenda,
            understanding,
            phase=phase,
            safety=safety,
            observer=observer,
        )
        merged = self._merge_events(safety_events, conv_events)
        decision = self._policy_decision(
            understanding,
            phase,
            merged,
            agenda,
            observer=observer,
        )
        return ResolverOutput(events=tuple(merged), decision=decision)

    def _merge_events(
        self,
        safety_events: Sequence[FsmEvent],
        conv_events: Sequence[FsmEvent],
    ) -> List[FsmEvent]:
        out: List[FsmEvent] = []
        for ev in safety_events:
            if ev not in out:
                out.append(ev)
        for ev in conv_events:
            if ev not in out:
                out.append(ev)
        if not out and not safety_events:
            out.append(FsmEvent.E_UNHANDLED)
        return out

    def _conversational_events(
        self,
        memory: ConversationMemory,
        agenda: AgendaManager,
        u: TurnUnderstanding,
        *,
        phase: CallPhase,
        safety: VerdictEvent | None,
        observer: ObserverPatch | None,
    ) -> List[FsmEvent]:
        if safety and (safety.kind or "") == "confirmed_red":
            return []

        # --- STT / silence ladder (before content) ---
        if u.input_reason in (SttReason.ECHO, SttReason.OFF_AGENDA):
            return [FsmEvent.E_ECHO]
        if u.input_reason == SttReason.LOW_CONF:
            return [FsmEvent.E_LOW_CONF]
        if u.input_reason == SttReason.STT_UNCERTAIN:
            if not self._uncertain_transcript_usable(u, agenda, memory, phase):
                return [FsmEvent.E_LOW_CONF]
        if u.speech_act == SpeechAct.EMPTY or u.input_reason == SttReason.EMPTY:
            return [FsmEvent.E_EMPTY]

        # Phone check-in («алло»/«ало») is never agenda content — any phase.
        if u.speech_act == SpeechAct.GREETING:
            return [FsmEvent.E_GREETING]

        # --- Priority stack (owner spec) ---
        # 1) Explicit user question — never unhandled in agenda states
        if u.speech_act == SpeechAct.QUESTION and u.clean_text:
            return [FsmEvent.E_SIDE_QUESTION]

        # 2) Correction / contradiction (observer or inline)
        if observer and (observer.corrections or observer.contradictions):
            return [FsmEvent.E_CORRECTION]
        if self._looks_like_correction(u.clean_text):
            return [FsmEvent.E_CORRECTION]

        # 3) Repair / meta confusion (clarify last phrase, not re-probe)
        if u.speech_act in (SpeechAct.REPAIR, SpeechAct.META_CONFUSION):
            return [FsmEvent.E_REPAIR]

        # 3a) Pending CHOICE — bare «да» must not close probe (before generic ack)
        pq = memory.pending_question
        if pq is not None and u.clean_text:
            valid, reason = validate_pending_answer(pq, u.clean_text)
            if not valid and reason == "choice_needs_pick":
                return [FsmEvent.E_CORRECTION]

        # 3b) Conversation-management ack
        if u.speech_act in (SpeechAct.ACK, SpeechAct.AFFIRMATION):
            if phase == CallPhase.SIDE_ANSWER:
                return [FsmEvent.E_SPEECH]
            if phase in (CallPhase.GOOD_PATH, CallPhase.BAD_PATH):
                if agenda.question_open and agenda.semantic_close(
                        u, clearing_symptom=memory.flags.clearing_symptom):
                    if self._probes_complete(agenda, phase, u, memory):
                        return [FsmEvent.E_PROBES_COMPLETE]
                    return [FsmEvent.E_PROBE_DONE]
                return [FsmEvent.E_SPEECH]
            if phase not in (CallPhase.LISTEN, CallPhase.CLARIFY):
                return [FsmEvent.E_ACK]

        # 5) Closing / refusal / help / worry
        if u.speech_act == SpeechAct.CLOSING_DIRECT:
            return [FsmEvent.E_CLOSING_DIRECT]
        if u.speech_act == SpeechAct.CLOSING:
            return [FsmEvent.E_CLOSING]
        if u.speech_act == SpeechAct.REFUSAL:
            return [FsmEvent.E_REFUSAL]
        if u.speech_act == SpeechAct.HELP:
            return [FsmEvent.E_HELP]
        if u.speech_act == SpeechAct.WORRY:
            return [FsmEvent.E_WELLNESS_BAD]

        # 6) Wellness contradiction while on GOOD_PATH
        if phase == CallPhase.GOOD_PATH and u.clean_text:
            band = classify_wellness(u.clean_text)
            if band in (WellnessBand.BAD, WellnessBand.MEDIUM, WellnessBand.CRITICAL):
                return [FsmEvent.E_WELLNESS_BAD]
            if u.mentions_symptom and not u.symptom_resolved:
                return [FsmEvent.E_WELLNESS_BAD]
            if observer and observer.contradictions:
                return [FsmEvent.E_CORRECTION]

        # 7) LISTEN wellness branch
        if phase == CallPhase.LISTEN and u.clean_text:
            if u.speech_act == SpeechAct.GREETING:
                return [FsmEvent.E_GREETING]
            band = classify_wellness(u.clean_text)
            agenda.set_wellness_from_text(u.clean_text)
            if band == WellnessBand.CRITICAL:
                return [FsmEvent.E_WELLNESS_CRITICAL]
            if band == WellnessBand.GOOD:
                return [FsmEvent.E_WELLNESS_GOOD]
            if band in (WellnessBand.BAD, WellnessBand.MEDIUM):
                return [FsmEvent.E_WELLNESS_BAD]
            if safety and (safety.kind or "") in ("uncertain_red", "possible_red"):
                return []
            if wellness_short_answer(u.clean_text) and memory.last_question:
                lq = memory.last_question.lower()
                if any(
                    w in lq
                    for w in (
                        "чувствуете", "поживаете", "настроение",
                        "самочувств", "как вы", "хорошо или плохо",
                    )
                ):
                    canon = wellness_short_answer(u.clean_text) or ""
                    if canon in ("всё плохо", "мне больно", "что-то болит", "так себе"):
                        return [FsmEvent.E_WELLNESS_BAD]
                    if canon in ("нужна помощь",):
                        return [FsmEvent.E_HELP]
                    return [FsmEvent.E_WELLNESS_GOOD]

        if phase == CallPhase.CLARIFY and u.clean_text:
            band = classify_wellness(u.clean_text)
            if band == WellnessBand.GOOD:
                return [FsmEvent.E_WELLNESS_GOOD]
            if band in (WellnessBand.BAD, WellnessBand.MEDIUM):
                return [FsmEvent.E_WELLNESS_BAD]
            if band == WellnessBand.CRITICAL:
                return [FsmEvent.E_WELLNESS_CRITICAL]

        if u.is_narrative or u.speech_act == SpeechAct.NARRATIVE:
            if should_reject_mixed_capture(
                    u.clean_text, last_question=memory.last_question or ""):
                return [FsmEvent.E_ECHO]
            if phase in (CallPhase.CLARIFY, CallPhase.GREETING):
                if u.clean_text:
                    return [FsmEvent.E_SPEECH]
                return [FsmEvent.E_EMPTY]
            if not agenda.question_open:
                band = classify_wellness(u.clean_text)
                if band in (WellnessBand.BAD, WellnessBand.MEDIUM, WellnessBand.CRITICAL):
                    return [FsmEvent.E_WELLNESS_BAD]
                if band == WellnessBand.GOOD:
                    return [FsmEvent.E_WELLNESS_GOOD]
                return [FsmEvent.E_SPEECH]
            if u.mentions_symptom:
                return [FsmEvent.E_WELLNESS_BAD]
            band = classify_wellness(u.clean_text)
            if band in (WellnessBand.BAD, WellnessBand.MEDIUM, WellnessBand.CRITICAL):
                return [FsmEvent.E_WELLNESS_BAD]
            if band == WellnessBand.GOOD and phase in (
                    CallPhase.GOOD_PATH, CallPhase.BAD_PATH, CallPhase.LISTEN):
                return [FsmEvent.E_WELLNESS_GOOD]
            return [FsmEvent.E_NARRATIVE]

        if phase == CallPhase.GREETING:
            return [FsmEvent.E_CALL_START]

        if phase == CallPhase.LISTEN:
            return [FsmEvent.E_SPEECH]

        if phase in (CallPhase.GOOD_PATH, CallPhase.BAD_PATH):
            if u.speech_act == SpeechAct.QUESTION:
                return [FsmEvent.E_SIDE_QUESTION]
            if agenda.semantic_close(u, clearing_symptom=memory.flags.clearing_symptom):
                if self._probes_complete(agenda, phase, u, memory):
                    return [FsmEvent.E_PROBES_COMPLETE]
                return [FsmEvent.E_PROBE_DONE]
            return [FsmEvent.E_SPEECH]

        if phase == CallPhase.CRITICAL_PATH:
            return [FsmEvent.E_WELLNESS_CRITICAL]

        if phase == CallPhase.RECORD_NOTIFY:
            return [FsmEvent.E_NOTIFY_DONE]

        if phase == CallPhase.CLOSING:
            if u.speech_act in (SpeechAct.CLOSING, SpeechAct.CLOSING_DIRECT):
                return [FsmEvent.E_CLOSING_DIRECT]
            return [FsmEvent.E_HANGUP]

        if phase == CallPhase.CLARIFY:
            if u.has_content:
                return [FsmEvent.E_SPEECH]
            return [FsmEvent.E_EMPTY]

        if phase == CallPhase.SIDE_ANSWER:
            return [FsmEvent.E_SPEECH]

        if phase in (CallPhase.SAFETY_CONFIRM, CallPhase.SAFETY_ACTIVE):
            return [FsmEvent.E_SPEECH]

        return [FsmEvent.E_UNHANDLED]

    def _looks_like_correction(self, text: str) -> bool:
        low = (text or "").lower()
        if not low:
            return False
        markers = (
            "не голова", "не спина", "имел в виду", "имела в виду",
            "не то", "исправ", "на самом деле",
        )
        return any(m in low for m in markers)

    def _uncertain_transcript_usable(
        self,
        u: TurnUnderstanding,
        agenda: AgendaManager,
        memory: ConversationMemory,
        phase: CallPhase,
    ) -> bool:
        text = (u.clean_text or "").strip()
        if not text or looks_like_garbage(text):
            return False
        if wellness_short_answer(text):
            return True
        if answers_wellness(text):
            return True
        if agenda.semantic_close(
                u, clearing_symptom=memory.flags.clearing_symptom):
            return True
        if u.word_count >= 2 and not looks_like_garbage(text):
            return True
        if phase == CallPhase.CLARIFY and memory.empty_turn_count > 0:
            return True
        return False

    def _probes_complete(
        self,
        agenda: AgendaManager,
        phase: CallPhase,
        u: TurnUnderstanding,
        memory: ConversationMemory,
    ) -> bool:
        from conversation_system.domain.wellness import good_path_probe_count

        if phase == CallPhase.GOOD_PATH:
            return agenda.good_probe_index >= good_path_probe_count() - 1
        if phase == CallPhase.BAD_PATH:
            return agenda.bad_symptom_probe_index >= bad_path_probe_count() - 1
        return True

    def _policy_decision(
        self,
        u: TurnUnderstanding,
        phase: CallPhase,
        events: Sequence[FsmEvent],
        agenda: AgendaManager,
        *,
        observer: ObserverPatch | None = None,
    ) -> PolicyDecision:
        directive = (observer.next_directive if observer else "") or ""
        allow_llm = False

        if phase in (
            CallPhase.RECORD_NOTIFY,
            CallPhase.CLOSING,
            CallPhase.SAFETY_CONFIRM,
            CallPhase.SAFETY_ACTIVE,
            CallPhase.TERMINAL,
            CallPhase.CRITICAL_PATH,
        ):
            if phase == CallPhase.RECORD_NOTIFY:
                goal = ResponseGoal(
                    kind=ResponseGoalKind.WRAP_UP,
                    scripted_only=True,
                )
            elif phase == CallPhase.CLOSING:
                goal = ResponseGoal(
                    kind=ResponseGoalKind.CLOSE,
                    scripted_only=True,
                )
            elif phase in (CallPhase.SAFETY_CONFIRM, CallPhase.SAFETY_ACTIVE):
                goal = ResponseGoal(
                    kind=ResponseGoalKind.SAFETY_CONFIRM,
                    scripted_only=True,
                )
            else:
                goal = ResponseGoal(
                    kind=ResponseGoalKind.SYMPTOM_FOLLOWUP,
                    scripted_only=True,
                )
            return PolicyDecision(
                primary_goal=goal,
                allow_llm=False,
                record_notes=(),
            )

        if FsmEvent.E_SAFETY_CONFIRMED in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.SAFETY_ACTIVE,
                scripted_only=True,
            )
        elif FsmEvent.E_SAFETY_UNCERTAIN in events \
                or FsmEvent.E_SAFETY_POSSIBLE in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.SAFETY_CONFIRM,
                scripted_only=True,
            )
        elif FsmEvent.E_SIDE_QUESTION in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.ANSWER_SIDE,
                allow_llm=True,
                scripted_only=False,
            )
            allow_llm = True
        elif FsmEvent.E_CORRECTION in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.SYMPTOM_FOLLOWUP,
                allow_llm=True,
                scripted_only=False,
            )
            allow_llm = True
        elif FsmEvent.E_EMPTY in events or FsmEvent.E_ECHO in events \
                or FsmEvent.E_LOW_CONF in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.CLARIFY,
                scripted_only=True,
            )
        elif FsmEvent.E_REPAIR in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.REPAIR,
                allow_llm=True,
                scripted_only=False,
                must_do="Повтори свой последний вопрос другими словами, без новой темы.",
            )
            allow_llm = True
        elif FsmEvent.E_ACK in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.ACKNOWLEDGE,
                allow_llm=True,
                scripted_only=False,
                must_do="Мягко продолжи разговор одним вопросом о самочувствии. "
                "Не говори что услышала или записала — связь могла быть плохой.",
            )
            allow_llm = True
        elif FsmEvent.E_NARRATIVE in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.ACKNOWLEDGE,
                topic="narrative",
                allow_llm=True,
                scripted_only=False,
            )
            allow_llm = True
        elif FsmEvent.E_GREETING in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.GREET,
                scripted_only=True,
            )
        elif FsmEvent.E_WELLNESS_BAD in events:
            focus = (u.symptom_focus or "") if u else ""
            goal = ResponseGoal(
                kind=ResponseGoalKind.SYMPTOM_FOLLOWUP,
                symptom_focus=focus,
                allow_llm=True,
                scripted_only=False,
                must_do=(
                    f"Уточни про {focus} одним вопросом."
                    if focus else "Уточни симптом одним вопросом."
                ),
            )
            allow_llm = True
        elif phase == CallPhase.GREETING:
            goal = ResponseGoal(
                kind=ResponseGoalKind.GREET,
                scripted_only=True,
            )
        elif FsmEvent.E_CLOSING_DIRECT in events or FsmEvent.E_CLOSING in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.CLOSE,
                scripted_only=True,
            )
        elif FsmEvent.E_REFUSAL in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.CLOSE,
                scripted_only=True,
            )
        elif FsmEvent.E_HELP in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.HELP_OFFER,
                scripted_only=True,
            )
        elif FsmEvent.E_WELLNESS_GOOD in events:
            goal = ResponseGoal(
                kind=ResponseGoalKind.ASK_TOPIC,
                allow_llm=True,
                scripted_only=False,
                must_do=agenda.slot_must_do(),
            )
            allow_llm = True
        elif phase == CallPhase.RECORD_NOTIFY:
            goal = ResponseGoal(
                kind=ResponseGoalKind.WRAP_UP,
                scripted_only=True,
            )
        else:
            goal = ResponseGoal(
                kind=ResponseGoalKind.ASK_TOPIC,
                allow_llm=True,
                scripted_only=False,
                must_do=agenda.slot_must_do(),
            )
            allow_llm = True

        if directive and goal.allow_llm:
            allow_llm = True
        elif directive and u.speech_act in (
            SpeechAct.QUESTION,
            SpeechAct.NARRATIVE,
            SpeechAct.REPAIR,
        ):
            allow_llm = True
            goal = ResponseGoal(
                kind=goal.kind,
                topic=goal.topic,
                symptom_focus=goal.symptom_focus,
                allow_llm=True,
                scripted_only=False,
            )

        notes: tuple[str, ...] = ()
        if u.mentions_symptom and u.symptom_focus:
            notes = (f"симптом: {u.symptom_focus}",)
        if directive:
            notes = notes + (f"directive:{directive[:80]}",)
        return PolicyDecision(
            primary_goal=goal,
            allow_llm=allow_llm,
            record_notes=notes,
        )
