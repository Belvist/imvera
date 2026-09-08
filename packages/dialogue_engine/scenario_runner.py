"""ScenarioRunner — deterministic dialogue regression without telephony."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from packages.dialogue.interpretation import interpret_user_turn
from packages.dialogue.state import DialogueState
from packages.dialogue_engine.context import InterpretContext
from packages.dialogue_engine.contextual_interpreter import contextual_interpret
from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.events import (
    CallStarted,
    DialogueEvent,
    InterpretationCompleted,
    PlayoutCompleted,
    User,
    UserTurnReceived,
)
from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic
from packages.dialogue_engine.invariants import (
    assert_turn_produced_outcome,
    check_all,
    count_opening_generations,
)
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.semantic import semantic_from_legacy
from packages.dialogue_engine.state import EngineState


@dataclass
class ScenarioResult:
    state: EngineState
    effects: list = field(default_factory=list)
    speak_effects: list[SpeakEffect] = field(default_factory=list)
    opening_count: int = 0
    partial_close: bool = False


class ScenarioRunner:
    def __init__(
        self,
        *,
        call_id: str = "scenario-1",
        elder_display_name: str = "Даниил",
        interpret_delay_s: float = 0.0,
    ) -> None:
        self.state = EngineState(call_id=call_id, elder_display_name=elder_display_name)
        self.effects: list = []
        self.interpret_delay_s = interpret_delay_s
        self._turn = 0

    def run(self, steps: list[DialogueEvent | User | str]) -> ScenarioResult:
        for step in steps:
            if isinstance(step, str):
                step = User(text=step)
            self._apply(step)
            check_all(self.state)
        speaks = [e for e in self.effects if isinstance(e, SpeakEffect)]
        return ScenarioResult(
            state=self.state,
            effects=list(self.effects),
            speak_effects=speaks,
            opening_count=count_opening_generations(self.effects),
            partial_close=any(
                e.intent == "partial_unresolved_close" for e in speaks
            ),
        )

    def _apply(self, step: DialogueEvent | User) -> None:
        if isinstance(step, User):
            self._turn += 1
            turn_id = f"u-{self._turn}"
            answer_slot = self.state.answer_context_slot()
            ctx = InterpretContext.from_engine_state(self.state, turn_id=turn_id)
            if step.semantic is not None:
                semantic = step.semantic
            else:
                sem, confident = contextual_interpret(step.text, ctx)
                if confident:
                    semantic = sem
                else:
                    fast_sem, fast_conf = fast_interpret_semantic(
                        step.text, answer_slot=answer_slot
                    )
                    if fast_conf:
                        semantic = fast_sem
                    else:
                        shadow = DialogueState(
                            call_id=self.state.call_id,
                            elder_display_name=self.state.elder_display_name,
                            family_id="fam-test",
                            fsm_state=self.state.fsm_state,
                            pending_slot=answer_slot,
                            pending_question_delivered=answer_slot is not None,
                            delivered_answer_slot=answer_slot,
                        )
                        interp = interpret_user_turn(shadow, step.text)
                        semantic = semantic_from_legacy(
                            interp, text=step.text, answer_slot=answer_slot
                        )

            if self.interpret_delay_s > 0:
                effect_id = f"ix-{self._turn}"
                self.state, pending = reduce(
                    self.state,
                    UserTurnReceived(
                        turn_id=turn_id,
                        text=step.text,
                        semantic=None,
                        effect_id=effect_id,
                        revision=self.state.revision,
                    ),
                )
                self._record(pending)
                time.sleep(self.interpret_delay_s)
                self.state, effects = reduce(
                    self.state,
                    InterpretationCompleted(
                        turn_id=turn_id,
                        effect_id=effect_id,
                        semantic=semantic,
                        revision=self.state.revision,
                    ),
                )
                assert_turn_produced_outcome(
                    text=step.text,
                    semantic=semantic,
                    effects=effects,
                    answer_slot=answer_slot,
                    call_closed=self.state.call_closed,
                )
            else:
                self.state, effects = reduce(
                    self.state,
                    UserTurnReceived(
                        turn_id=turn_id,
                        text=step.text,
                        semantic=semantic,
                        revision=self.state.revision,
                    ),
                )
            assert_turn_produced_outcome(
                text=step.text,
                semantic=semantic,
                effects=effects,
                answer_slot=answer_slot,
                call_closed=self.state.call_closed,
            )
            self._record(effects)
            return

        self.state, effects = reduce(self.state, step)
        self._record(effects)
        if isinstance(step, CallStarted):
            self._auto_deliver(effects)

    def _record(self, effects: list) -> None:
        self.effects.extend(effects)
        self._auto_deliver(effects)

    def _auto_deliver(self, effects: list) -> None:
        for effect in effects:
            if not isinstance(effect, SpeakEffect):
                continue
            if effect.marks_question or effect.intent == "opening_wellness":
                self.state, extra = reduce(
                    self.state,
                    PlayoutCompleted(
                        generation=effect.generation,
                        question_id=effect.question_id,
                        revision=self.state.revision,
                    ),
                )
                self.effects.extend(extra)
