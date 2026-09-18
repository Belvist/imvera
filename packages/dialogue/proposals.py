"""Neutral TurnProposal builders shared by engine adapters and legacy lab code."""

from __future__ import annotations

from typing import Any

from packages.contracts.turn import TurnProposal


def terminal_noop(state: Any, turn_id: int, generation_id: str) -> TurnProposal:
    """Return an empty terminal proposal without mutating dialogue state."""
    return TurnProposal(
        turn_id=turn_id,
        generation_id=generation_id,
        speech="",
        intent="terminal_noop",
        fsm_state=state.fsm_state,
        mandatory_remaining=state.mandatory_remaining(),
    )
