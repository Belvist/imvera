"""CorpusRunner — production DialogueEngine path with invariant tracking."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from packages.contracts.enums import SlotStatus
from packages.dialogue.interpretation import interpret_user_turn
from packages.dialogue.state import DialogueState
from packages.dialogue_engine.effects import SpeakEffect, TimerEffect
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import User
from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic
from packages.dialogue_engine.invariants import count_opening_generations
from packages.dialogue_engine.semantic import semantic_from_legacy
from packages.dialogue_engine.corpus.schema import (
    CorpusInvariantReport,
    CorpusStep,
    DeliverPlayout,
    DeliverPlayoutDuplicate,
    DeferLastSpeak,
    ExpectSlot,
    ExpectSpeakIntent,
    ExpectTerminal,
    FireTimerExpired,
    FullDialogueScenario,
    StaleLastSpeak,
    UserStep,
)


@dataclass
class CorpusRunResult:
    scenario_id: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    invariants: CorpusInvariantReport = field(default_factory=CorpusInvariantReport)
    speak_intents: list[str] = field(default_factory=list)
    opening_count: int = 0
    partial_close: bool = False
    reached_goodbye_final: bool = False


class CorpusRunner:
    """Run one FullDialogueScenario through DialogueEngine (production reducer path)."""

    def __init__(
        self,
        scenario: FullDialogueScenario,
        *,
        interpret_delay_s: float = 0.01,
    ) -> None:
        self.scenario = scenario
        self.engine = DialogueEngine(
            call_id=scenario.id,
            elder_display_name="Даниил",
        )
        self.engine.state.wellness_probes_enabled = False
        self.interpret_delay_s = interpret_delay_s
        self.effects: list = []
        self.speak_effects: list[SpeakEffect] = []
        self.errors: list[str] = []
        self.invariants = CorpusInvariantReport()
        self._turn = 0
        self._pending_speaks: list[SpeakEffect] = []
        self._last_delivered: SpeakEffect | None = None
        self._deferred: SpeakEffect | None = None
        self._duplicate_mutations = 0
        self._revision_at_last_deliver = 0

    def run(self) -> CorpusRunResult:
        self._start_call()
        for step in self.scenario.steps:
            self._execute(step)

        intents = [e.intent for e in self.speak_effects]
        opening_count = count_opening_generations(self.effects)
        partial = "partial_unresolved_close" in intents
        reached_final = "goodbye_final" in intents and self.engine.state.goodbye_confirmed

        if opening_count != 1:
            self.invariants.opening_replays = opening_count - 1
            self.errors.append(f"opening_count={opening_count} expected 1")
        if partial and not self.scenario.allow_partial_close:
            self.invariants.premature_unresolved_close = 1
            self.errors.append("partial_unresolved_close")
        if not reached_final and not self.scenario.allow_partial_close:
            self.invariants.failed_to_goodbye_final = 1
            self.errors.append("goodbye_final not reached")

        self._check_slot_order()
        self._check_wellness_ack(intents)

        return CorpusRunResult(
            scenario_id=self.scenario.id,
            passed=not self.errors,
            errors=list(self.errors),
            invariants=self.invariants,
            speak_intents=intents,
            opening_count=opening_count,
            partial_close=partial,
            reached_goodbye_final=reached_final,
        )

    def _start_call(self) -> None:
        self._record(self.engine.start())
        opening = self.engine.pop_speak_effect()
        if opening is not None:
            self._deliver_speak(opening)

    def _execute(self, step: CorpusStep) -> None:
        if isinstance(step, UserStep):
            self._user_turn(step.text, delayed=step.delayed)
        elif isinstance(step, DeliverPlayout):
            if step.include_summary:
                self._deliver_pending_non_question()
            else:
                self._deliver_next_question()
        elif isinstance(step, DeliverPlayoutDuplicate):
            if self._last_delivered is not None:
                rev_before = self.engine.revision
                self._record(
                    self.engine.on_playout_completed(
                        self._last_delivered.generation,
                        self._last_delivered.question_id,
                    )
                )
                if self.engine.revision != rev_before:
                    self._duplicate_mutations += 1
                    self.invariants.duplicate_playout_mutations += 1
        elif isinstance(step, FireTimerExpired):
            timer_id = step.timer_id or self._default_timer_id()
            self._record(self.engine.on_timer_expired(timer_id))
            self._drain_speak_effects()
        elif isinstance(step, DeferLastSpeak):
            if self._pending_speaks:
                effect = self._pending_speaks[-1]
                self._deferred = effect
                self._pending_speaks.pop()
                self._record(self.engine.on_delivery_deferred(effect))
        elif isinstance(step, StaleLastSpeak):
            if self._deferred is not None:
                self._record(self.engine.on_speak_effect_stale(self._deferred))
                self._deferred = None
                self._drain_speak_effects()
        elif isinstance(step, ExpectSlot):
            status = self.engine.state.slots.get(step.slot)
            if step.filled and status != SlotStatus.FILLED:
                self.errors.append(f"slot {step.slot} not FILLED ({status})")
            elif not step.filled and status == SlotStatus.FILLED:
                self.errors.append(f"slot {step.slot} unexpectedly FILLED")
        elif isinstance(step, ExpectSpeakIntent):
            if not self._pending_speaks:
                self.errors.append(f"expected speak intent {step.intent}, none pending")
            elif self._pending_speaks[-1].intent != step.intent:
                got = self._pending_speaks[-1].intent
                self.errors.append(f"expected intent {step.intent}, got {got}")
        elif isinstance(step, ExpectTerminal):
            if step.intent == "goodbye_final":
                if not self.engine.state.goodbye_confirmed:
                    self.errors.append("goodbye_confirmed=false at terminal")
            intents = [e.intent for e in self.speak_effects]
            if step.intent not in intents:
                self.errors.append(f"terminal intent {step.intent} not in speak effects")

    def _user_turn(self, text: str, *, delayed: bool) -> None:
        self._turn += 1
        turn_id = f"u-{self._turn}"
        answer_slot = self.engine.answer_context_slot()
        fast_sem, confident = fast_interpret_semantic(text, answer_slot=answer_slot)
        if confident:
            semantic = fast_sem
        else:
            shadow = DialogueState(
                call_id=self.engine.state.call_id,
                elder_display_name=self.engine.state.elder_display_name,
                family_id="fam-corpus",
                fsm_state=self.engine.state.fsm_state,
                pending_slot=answer_slot,
                pending_question_delivered=answer_slot is not None,
                delivered_answer_slot=answer_slot,
            )
            interp = interpret_user_turn(shadow, text)
            semantic = semantic_from_legacy(
                interp, text=text, answer_slot=answer_slot
            )

        if delayed and self.interpret_delay_s > 0:
            effect_id = self.engine.begin_interpret(turn_id)
            self._record(
                self.engine.on_user_turn(
                    turn_id, text, None, effect_id=effect_id, defer=True
                )
            )
            time.sleep(self.interpret_delay_s)
            self._record(
                self.engine.on_interpretation_completed(
                    turn_id, effect_id, semantic
                )
            )
        else:
            self._record(
                self.engine.on_user_turn(turn_id, text, semantic)
            )
        self._drain_speak_effects()

    def _drain_speak_effects(self) -> None:
        while True:
            speak = self.engine.pop_speak_effect()
            if speak is None:
                break
            self.speak_effects.append(speak)
            self._pending_speaks.append(speak)
        timer = self.engine.pop_timer_effect()
        if timer is not None:
            self.effects.append(timer)

    def _deliver_next_question(self) -> None:
        if not self._pending_speaks:
            self.errors.append("DeliverPlayout: no pending speak")
            return
        effect = self._pending_speaks.pop(0)
        if effect.marks_question or effect.intent == "opening_wellness":
            self._deliver_speak(effect)
        else:
            self._pending_speaks.insert(0, effect)

    def _deliver_pending_non_question(self) -> None:
        while self._pending_speaks:
            effect = self._pending_speaks.pop(0)
            if effect.marks_question:
                self._pending_speaks.insert(0, effect)
                break
            self._last_delivered = effect
            self._record(
                self.engine.on_playout_completed(
                    effect.generation,
                    effect.question_id,
                )
            )
            self._drain_speak_effects()

    def _deliver_speak(self, effect: SpeakEffect) -> None:
        self._last_delivered = effect
        self._revision_at_last_deliver = self.engine.revision
        self._record(
            self.engine.on_playout_completed(
                effect.generation,
                effect.question_id,
            )
        )
        self._drain_speak_effects()

    def _default_timer_id(self) -> str:
        slot = self.engine.state.waiting_on_slot or self.engine.state.answer_context_slot()
        return f"wait-{slot}" if slot else "wait-wellness"

    def _record(self, effects: list) -> None:
        if effects:
            self.effects.extend(effects)

    def _check_slot_order(self) -> None:
        order = ("wellness", "mood", "sleep", "plans")
        filled_order = [s for s in order if self.engine.state.slots.get(s) == SlotStatus.FILLED]
        if filled_order != list(order):
            self.errors.append(f"slot fill order {filled_order} != {list(order)}")

    def _check_wellness_ack(self, intents: list[str]) -> None:
        if self.scenario.family == "self_correction":
            return
        if "check_mood" not in intents:
            return
        from packages.dialogue_engine.questions import wellness_ack

        expected_prefix = wellness_ack(value=self.scenario.answers.wellness)
        mood_speaks = [e.text for e in self.speak_effects if e.intent == "check_mood"]
        if mood_speaks and not mood_speaks[0].startswith(expected_prefix):
            self.errors.append(
                f"wellness ack expected {expected_prefix!r} "
                f"got {mood_speaks[0][:48]!r}"
            )
