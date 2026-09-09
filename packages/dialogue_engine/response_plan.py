"""Response planning — acknowledgement + next unresolved goal question."""

from __future__ import annotations

from packages.dialogue_engine import questions
from packages.dialogue_engine.context import ResponsePlan, SlotCandidate
from packages.dialogue_engine.state import EngineState


def build_response_plan(
    state: EngineState,
    *,
    newly_filled: list[str],
    next_slot: str,
) -> ResponsePlan:
    ack = _acknowledge_fills(state, newly_filled)
    question = questions.slot_question(next_slot, state=state)
    return ResponsePlan(
        acknowledge=ack,
        facts_to_reference=list(newly_filled),
        next_slot=next_slot,
        mandatory_question=question,
        tone="warm",
    )


def compose_speech(plan: ResponsePlan) -> str:
    parts = [p for p in (plan.acknowledge, plan.mandatory_question) if p]
    return " ".join(parts)


def _acknowledge_fills(state: EngineState, filled: list[str]) -> str:
    if not filled:
        return ""

    if "wellness" in filled:
        rec = state.slot_records.get("wellness")
        pol = rec.polarity if rec else None
        val = rec.value if rec else state.slot_values.get("wellness", "")
        return questions.wellness_ack(polarity=pol, value=val)

    if "sleep" in filled:
        rec = state.slot_records.get("sleep")
        pol = rec.polarity if rec else None
        if pol == "negative" or _looks_bad_sleep(rec.value if rec else ""):
            return "Понимаю, ночь была тяжёлая."

    if "mood" in filled:
        rec = state.slot_records.get("mood")
        pol = rec.polarity if rec else None
        if pol == "negative":
            return "Понимаю."

    if "plans" in filled:
        return "Хорошо, поняла."

    return ""


def _looks_bad_sleep(text: str) -> bool:
    t = text.lower()
    return any(x in t for x in ("не спал", "плохо", "мало", "беспокойн", "почти не"))


def slot_polarity_from_candidate(cand: SlotCandidate) -> str | None:
    return cand.polarity
