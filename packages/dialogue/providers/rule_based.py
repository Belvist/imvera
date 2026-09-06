"""Rule-based interpretation provider — deterministic baseline for product path."""

from packages.contracts.enums import AsrQuality
from packages.contracts.interpretation import TurnInterpretation
from packages.dialogue.interpretation import (
    UserInterpretation,
    interpret_user_turn,
    to_turn_interpretation,
)
from packages.dialogue.state import DialogueState


class RuleBasedInterpretationProvider:
    """Synchronous semantic baseline; LLM providers implement the same contract."""

    provider_name: str = "rule_baseline_v1"

    def interpret_turn(
        self,
        state: DialogueState,
        *,
        call_id: str,
        turn_id: int,
        user_text: str,
        asr_quality: AsrQuality = AsrQuality.GOOD,
    ) -> tuple[UserInterpretation, TurnInterpretation]:
        state_version = state.state_version
        interp = interpret_user_turn(state, user_text)
        contract = to_turn_interpretation(
            state,
            turn_id,
            user_text,
            interp,
            state_version=state_version,
            asr_quality=asr_quality,
        )
        return interp, contract
