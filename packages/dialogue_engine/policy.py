"""Goal policy — deterministic slot/attempt rules."""

from __future__ import annotations

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.context import SlotCandidate, SlotValue
from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
from packages.dialogue_engine.state import EngineState, MAX_SLOT_ATTEMPTS

_MAX_UNCLEAR = 2


def apply_slot_answer(
    state: EngineState,
    slot: str,
    value: str,
    *,
    turn_id: str = "",
    polarity: str | None = None,
    confidence: float = 0.9,
    correction: bool = False,
) -> None:
    prev = state.slot_records.get(slot)
    if prev and correction:
        state.slot_corrections.append(
            {
                "slot": slot,
                "old": prev.value,
                "new": value,
                "source_turn": turn_id,
            }
        )
    state.slots[slot] = SlotStatus.FILLED
    state.slot_values[slot] = value
    state.slot_records[slot] = SlotValue(
        value=value,
        confidence=confidence,
        source_turn_id=turn_id,
        source_text=value,
        polarity=polarity,
        confirmed=False,
    )
    goal = state.ensure_goal(slot)
    goal.status = SlotStatus.FILLED
    state.slot_unclear_counts.pop(slot, None)


def fill_from_semantic(
    state: EngineState, semantic: SemanticTurn, *, turn_id: str = ""
) -> list[str]:
    """Apply all slot candidates; return list of newly filled slots."""
    if semantic.act != SemanticAct.ANSWER:
        return []
    turn_id = turn_id or semantic.answers_to or ""
    filled: list[str] = []
    if semantic.slots:
        for slot, cand in semantic.slots.items():
            if state.slots.get(slot) != SlotStatus.OPEN:
                continue
            apply_slot_answer(
                state,
                slot,
                cand.value,
                turn_id=turn_id,
                polarity=cand.polarity,
                confidence=cand.confidence,
                correction=semantic.correction,
            )
            filled.append(slot)
        return filled
    slot = semantic.target_slot
    if not slot or state.slots.get(slot) != SlotStatus.OPEN:
        return []
    apply_slot_answer(
        state,
        slot,
        semantic.value or semantic.source_quote,
        turn_id=turn_id,
        polarity=semantic.polarity,
        confidence=semantic.confidence,
        correction=semantic.correction,
    )
    return [slot]


def may_close_partial(state: EngineState, slot: str) -> bool:
    goal = state.ensure_goal(slot)
    if state.playing_question is not None or state.planned_question is not None:
        return False
    count = state.slot_unclear_counts.get(slot, 0)
    if count <= _MAX_UNCLEAR:
        return False
    return goal.delivered_attempts >= goal.max_attempts


def can_ask_slot(state: EngineState, slot: str) -> bool:
    goal = state.ensure_goal(slot)
    if state.slots.get(slot) != SlotStatus.OPEN:
        return False
    if goal.delivered_attempts >= goal.max_attempts:
        return False
    return True


def release_reservation(state: EngineState, slot: str) -> None:
    goal = state.ensure_goal(slot)
    goal.reserved_question_id = None


def reserve_question(state: EngineState, slot: str, question_id: str) -> bool:
    goal = state.ensure_goal(slot)
    if goal.delivered_attempts >= goal.max_attempts:
        return False
    if goal.reserved_question_id and goal.reserved_question_id != question_id:
        if state.delivered_question is None:
            goal.reserved_question_id = None
        else:
            return False
    goal.reserved_question_id = question_id
    return True


def mark_question_delivered(state: EngineState, slot: str, question_id: str) -> None:
    goal = state.ensure_goal(slot)
    if goal.reserved_question_id != question_id:
        return
    goal.delivered_attempts += 1
    goal.reserved_question_id = None
