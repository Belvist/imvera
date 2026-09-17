from __future__ import annotations

from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import CallStarted, DialogueEvent, User
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn
from packages.dialogue_engine.turn_understanding import RichUserTurn


class ConversationRunner(ScenarioRunner):
    def __init__(self, *, call_id: str) -> None:
        super().__init__(call_id=call_id, elder_display_name="Тест")
        self.engine = DialogueEngine(call_id=call_id, elder_display_name="Тест")
        self.state = self.engine.state
        self.last_turn: RichUserTurn | None = None

    def _apply(self, step: DialogueEvent | User) -> None:
        if isinstance(step, CallStarted):
            self._record(self.engine.start())
        elif isinstance(step, User):
            assert step.rich_turn is None and step.semantic is None
            self._turn += 1
            uid = f"u-{self._turn}"
            slot = self.engine.answer_context_slot()
            parsed = interpret(
                step.text, utterance_id=uid, engine_state=self.engine.state, answer_slot=slot
            )
            self.last_turn = kernel_to_rich_turn(
                parsed, answer_slot=slot, engine_state=self.engine.state
            )
            self._record(self.engine.on_user_turn(uid, step.text, rich_turn=self.last_turn))
        else:
            raise TypeError(f"Unsupported conversation step: {type(step).__name__}")
        self.state = self.engine.state

    def _auto_deliver(self, effects: list) -> None:
        for _ in range(16):
            speaks = self.engine.drain_speak_effects()
            if not speaks:
                self.state = self.engine.state
                return
            for effect in speaks:
                assert self.engine.is_speak_effect_valid(effect)
                self.effects.extend(
                    self.engine.on_playout_started(effect.generation, effect.question_id)
                )
                self.effects.extend(
                    self.engine.on_playout_completed(effect.generation, effect.question_id)
                )
        raise AssertionError("Playout did not quiesce within 16 deliveries")
