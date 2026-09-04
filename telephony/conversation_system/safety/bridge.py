"""SafetyBridge — adapter to SafetyEngine with confirm-gate policy."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Sequence

from conversation_system.domain.fsm_types import FsmEvent
from conversation_system.domain.understanding import SpeechAct, TurnUnderstanding
from conversation_system.memory.state import ConversationMemory
from conversation_system.turn._cleaners import short_real_answer
from conversation_system.domain.wellness import WellnessBand, classify_wellness, is_symptom_intensifier
from core.safety_engine import Observation, SafetyEngine, VerdictEvent


@dataclass(frozen=True)
class SafetyBridgeResult:
    """Safety observation + mapped FSM events (priority order)."""

    verdict: VerdictEvent
    events: tuple[FsmEvent, ...]
    safety_status: str
    verdict_label: str = "ok"


class SafetyBridge:
    """Per-call shared SafetyEngine — one instance per ConversationSession."""

    _YES_NO_RE = re.compile(
        r"\?\s*$|(?:^|\s)(?:да|нет|ага|неа|yes|no)(?:\s|$)",
        re.I,
    )

    def __init__(self, engine: SafetyEngine | None = None) -> None:
        self._engine = engine or SafetyEngine()

    @property
    def engine(self) -> SafetyEngine:
        return self._engine

    def observe(
        self,
        memory: ConversationMemory,
        understanding: TurnUnderstanding,
        *,
        stt_confidence: float | None = None,
    ) -> VerdictEvent:
        """Feed one turn to SafetyEngine — never raises."""
        return self._engine.observe(Observation(
            question=memory.last_question or None,
            raw_text=understanding.clean_text or None,
            confidence=stt_confidence,
        ))

    def process(
        self,
        memory: ConversationMemory,
        understanding: TurnUnderstanding,
        *,
        phase: str,
        stt_confidence: float | None = None,
    ) -> SafetyBridgeResult:
        """Observe + map verdict to FSM events with confirm-gate."""
        if self._symptom_detail_answer(memory, understanding, phase):
            self._engine.defer_confirmation_for_symptom_detail()
        verdict = self.observe(memory, understanding, stt_confidence=stt_confidence)
        events = self.map_to_events(
            verdict, memory, understanding, phase=phase)
        status = self._status_from_verdict(verdict)
        label = self._verdict_label(verdict)
        return SafetyBridgeResult(
            verdict=verdict,
            events=events,
            safety_status=status,
            verdict_label=label,
        )

    def map_to_events(
        self,
        verdict: VerdictEvent,
        memory: ConversationMemory,
        understanding: TurnUnderstanding,
        *,
        phase: str,
    ) -> tuple[FsmEvent, ...]:
        """Map SafetyEngine output to FSM events — RED never downplayed."""
        kind = (verdict.kind or "").strip()

        if kind == "confirmed_red":
            return (FsmEvent.E_SAFETY_CONFIRMED,)

        text = (understanding.clean_text or "").strip()
        if text and phase in (
            "listen", "greeting", "good_path", "bad_path", "clarify", "side_answer",
        ):
            band = classify_wellness(text)
            if band == WellnessBand.CRITICAL:
                return ()
            if band == WellnessBand.GOOD and kind in (
                "unknown", "ok", "no_speech", "uncertain_red", "possible_red",
            ):
                return ()
            if band in (WellnessBand.BAD, WellnessBand.MEDIUM) and kind in (
                "possible_red", "uncertain_red",
            ):
                return ()

        if kind == "uncertain_red":
            if phase == "safety_confirm" and self._confirms_danger(understanding, memory):
                return (FsmEvent.E_SAFETY_CONFIRMED,)
            if phase == "safety_confirm" and self._denies_danger(understanding):
                return (FsmEvent.E_SAFETY_CLEARED,)
            return (FsmEvent.E_SAFETY_UNCERTAIN,)

        if kind == "possible_red":
            if phase in ("safety_confirm", "safety_active"):
                if self._confirms_danger(understanding, memory):
                    return (FsmEvent.E_SAFETY_CONFIRMED,)
                if self._denies_danger(understanding):
                    return (FsmEvent.E_SAFETY_CLEARED,)
            return (FsmEvent.E_SAFETY_POSSIBLE,)

        if kind in ("ok", "unknown", "no_speech") and phase.startswith("safety"):
            if self._denies_danger(understanding) or understanding.symptom_resolved:
                return (FsmEvent.E_SAFETY_CLEARED,)

        if kind == "help_request" and memory.active_symptom \
                and is_symptom_intensifier(understanding.clean_text):
            return ()

        return ()

    def _symptom_detail_answer(
        self,
        memory: ConversationMemory,
        understanding: TurnUnderstanding,
        phase: str,
    ) -> bool:
        """Intensity / timing answer to an open symptom probe — not danger confirm."""
        text = (understanding.clean_text or "").strip()
        if not text or not memory.active_symptom:
            return False
        if phase not in (
            "listen", "good_path", "bad_path", "clarify", "side_answer",
        ):
            return False
        if is_symptom_intensifier(text):
            return True
        if phase == "bad_path" and understanding.word_count <= 3:
            return True
        return False

    def confirm_gate_allows_yes(self, memory: ConversationMemory) -> bool:
        """«Да» confirms danger only on explicit yes/no control question."""
        q = (memory.last_question or "").strip()
        if not q or "?" not in q:
            return False
        low = q.lower()
        if not any(w in low for w in ("да или нет", "ответьте", "скажите")) \
                and not re.search(r"\?\s*$", q):
            return False
        return bool(re.search(
            r"(опасност|срочн|плохо|помощ|серьёз|безопасност|верно|действительно)",
            low,
        ))

    def _confirms_danger(
        self,
        understanding: TurnUnderstanding,
        memory: ConversationMemory,
    ) -> bool:
        if not self.confirm_gate_allows_yes(memory):
            return False
        text = understanding.clean_text.lower()
        if short_real_answer(text) in ("да", "yes"):
            return True
        if understanding.speech_act == SpeechAct.AFFIRMATION \
                and re.search(r"^(?:да|ага|yes)\b", text):
            return True
        return False

    def _denies_danger(self, understanding: TurnUnderstanding) -> bool:
        text = understanding.clean_text.lower()
        if short_real_answer(text) in ("нет", "no", "помощь не нужна"):
            return True
        if understanding.speech_act == SpeechAct.REFUSAL:
            return True
        if re.search(r"^нет\b", text):
            return True
        return False

    def _status_from_verdict(self, verdict: VerdictEvent) -> str:
        kind = verdict.kind or "unknown"
        mapping = {
            "confirmed_red": "alert",
            "uncertain_red": "attention",
            "possible_red": "attention",
            "help_request": "attention",
            "third_person": "attention",
            "ok": "ok",
            "unknown": "unknown",
            "no_speech": "unknown",
            "frozen": "frozen",
        }
        return mapping.get(kind, kind)

    def _verdict_label(self, verdict: VerdictEvent) -> str:
        kind = verdict.kind or "ok"
        if kind == "confirmed_red":
            return "alert"
        if kind in ("uncertain_red", "possible_red"):
            return "attention"
        return "ok"

    def priority_events(
        self,
        safety_events: Sequence[FsmEvent],
        resolver_events: Sequence[FsmEvent],
    ) -> List[FsmEvent]:
        """Safety events always precede conversational events."""
        out: List[FsmEvent] = []
        for ev in safety_events:
            if ev not in out:
                out.append(ev)
        for ev in resolver_events:
            if ev not in out:
                out.append(ev)
        return out
