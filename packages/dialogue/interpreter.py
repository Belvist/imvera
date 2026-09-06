"""Interpreter facade — single entry for turn understanding."""

from packages.contracts.enums import AsrQuality
from packages.contracts.interpretation import TurnInterpretation
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.providers.rule_based import RuleBasedInterpretationProvider
from packages.dialogue.state import DialogueState


class Interpreter:
    """Wraps InterpretationProvider; default is rule baseline until LLM is benchmarked."""

    def __init__(self, provider: RuleBasedInterpretationProvider | None = None) -> None:
        self._provider = provider or RuleBasedInterpretationProvider()

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    def interpret(
        self,
        state: DialogueState,
        user_text: str,
        turn_id: int,
        asr_quality: AsrQuality = AsrQuality.GOOD,
    ) -> tuple[UserInterpretation, TurnInterpretation]:
        return self._provider.interpret_turn(
            state,
            call_id=state.call_id,
            turn_id=turn_id,
            user_text=user_text,
            asr_quality=asr_quality,
        )
