"""Goal policy — deterministic slot/attempt rules."""

from __future__ import annotations

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.context import SlotValue
from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
from packages.dialogue_engine.state import EngineState, GoalLifecycle

_MAX_UNCLEAR = 2


def apply_slot_answer(
    state: EngineState,
    slot: str,
    value: str,
    *,
    turn_id: str = "",
    source_text: str | None = None,
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
    grounded = source_text or value
    state.slot_records[slot] = SlotValue(
        value=value,
        confidence=confidence,
        source_turn_id=turn_id,
        source_text=grounded,
        polarity=polarity,
        confirmed=False,
    )
    goal = state.ensure_goal(slot)
    goal.status = SlotStatus.FILLED
    goal.lifecycle = GoalLifecycle.SATISFIED
    goal.answer = value
    # SlotRecord is the evidence owner for slot answers; mission_result also
    # reads it. Keep goal progress coherent with that same accepted write.
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
            if slot in ("wellness", "mood", "sleep") and _is_other_person_only(
                semantic.source_quote
            ):
                # Someone else's complaint is not the speaker's fact.
                continue
            apply_slot_answer(
                state,
                slot,
                cand.value,
                turn_id=turn_id,
                source_text=semantic.source_quote,
                polarity=cand.polarity,
                confidence=cand.confidence,
                correction=semantic.correction,
            )
            filled.append(slot)
        return filled
    slot = semantic.target_slot
    if not slot or state.slots.get(slot) != SlotStatus.OPEN:
        return []
    if slot in ("wellness", "mood", "sleep") and _is_other_person_only(
        semantic.source_quote
    ):
        return []
    apply_slot_answer(
        state,
        slot,
        semantic.value or semantic.source_quote,
        turn_id=turn_id,
        source_text=semantic.source_quote,
        polarity=semantic.polarity,
        confidence=semantic.confidence,
        correction=semantic.correction,
    )
    return [slot]


def _is_other_person_only(text: str) -> bool:
    """Someone else's complaint without any speaker signal."""
    import re

    from packages.dialogue_engine.semantic_kernel.lexicon import (
        OTHER_PERSON_MARKERS,
    )

    low = (text or "").lower().replace("ё", "е")
    if not any(m in low for m in OTHER_PERSON_MARKERS):
        return False
    return not bool(
        re.search(r"\b(я|мне|меня|мной|у\s+меня|мною|сам|сама)\b", low)
    )


def may_close_partial(state: EngineState, slot: str) -> bool:
    from packages.dialogue_engine.protocol.acts import is_forbidden

    # CDK Step 2: a recorded DECLINE forbids the give-up close — "не
    # получилось узнать" is factually wrong after "nothing bothers".
    # Normal close (ITS/summary) still happens via the ladder.
    if is_forbidden(state, "concern_probe"):
        return False
    goal = state.ensure_goal(slot)
    if state.playing_question is not None or state.planned_question is not None:
        return False
    count = state.slot_unclear_counts.get(slot, 0)
    if count <= _MAX_UNCLEAR:
        return False
    return goal.delivered_attempts >= goal.max_attempts


def can_ask_slot(state: EngineState, slot: str) -> bool:
    goal = state.ensure_goal(slot)
    if slot.startswith("probe_") or slot.startswith("episode_"):
        return goal.delivered_attempts < goal.max_attempts
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
    from packages.dialogue_engine.state import GoalLifecycle

    if goal.lifecycle in {
        GoalLifecycle.AVAILABLE,
        GoalLifecycle.UNSEEN,
        GoalLifecycle.ACTIVE,
        GoalLifecycle.ASKED,
    }:
        goal.lifecycle = GoalLifecycle.ANSWER_PENDING
