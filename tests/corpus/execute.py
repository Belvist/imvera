"""Execute one corpus scenario against CallSession (ONE dialogue engine)."""

from __future__ import annotations

import time

from packages.contracts.enums import SlotStatus
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from tests.corpus.invariants import check_turn_invariants, pending_slot
from tests.corpus.models import Scenario, ScenarioResult, TurnTrace


def _daily_session(call_id: str) -> CallSession:
    session = CallSession(
        call_id=call_id,
        family_id="corpus-family",
        elder_display_name="Бабушка",
        store=InMemoryCallRecordStore(),
    )
    start = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(start.proposal.generation_id)
    assert pending_slot(session) == "wellness"
    return session


def _mark_spoken(session: CallSession) -> None:
    gen = session.state.pending_action_id
    if gen:
        session.mark_spoken_action(gen)


def _slot_map(session: CallSession) -> dict[str, str]:
    return {k: v.value for k, v in session.state.slots.items()}


def run_scenario(scenario: Scenario) -> ScenarioResult:
    """Run setup + measured turns; assert expectations + hard invariants."""
    t0 = time.perf_counter()
    errors: list[str] = []
    traces: list[TurnTrace] = []

    session = _daily_session(f"corpus-{scenario.id}")
    recent_speeches: list[str] = []

    for text in scenario.setup_turns:
        before = dict(session.state.slots)
        result = session.handle_user_text(text)
        _mark_spoken(session)
        recent_speeches.append(result.proposal.speech or "")
        errors.extend(
            check_turn_invariants(
                session,
                text,
                before,
                recent_speeches=recent_speeches,
            )
        )

    for text in scenario.turns:
        before = dict(session.state.slots)
        result = session.handle_user_text(text)
        _mark_spoken(session)
        speech = result.proposal.speech or ""
        recent_speeches.append(speech)
        traces.append(
            TurnTrace(
                user_text=text,
                intent=result.proposal.intent,
                judgement=result.interpretation.judgement.value,
                dialogue_act=result.interpretation.dialogue_act.value,
                pending_slot=pending_slot(session),
                slots=_slot_map(session),
                speech=speech,
            )
        )
        errors.extend(
            check_turn_invariants(
                session,
                text,
                before,
                recent_speeches=recent_speeches,
            )
        )
        for slot in scenario.never_fill:
            if session.state.slots.get(slot) == SlotStatus.FILLED:
                # Allow FILLED only if it was already filled before this measured turn.
                if before.get(slot) != SlotStatus.FILLED:
                    errors.append(
                        f"never_fill: slot {slot} became FILLED on {text!r}"
                    )

    final_slots = _slot_map(session)
    for slot, expected in scenario.expect_slots.items():
        actual = final_slots.get(slot)
        if actual != expected:
            errors.append(
                f"slot {slot}: expected {expected}, got {actual} "
                f"(last intent={traces[-1].intent if traces else None})"
            )

    if scenario.expect_intent_in and traces:
        last_intent = traces[-1].intent
        allowed = scenario.expect_intent_in
        matched = last_intent in allowed or any(
            pattern.endswith("*") and last_intent.startswith(pattern[:-1])
            for pattern in allowed
        )
        if not matched:
            errors.append(
                f"intent: expected one of {allowed}, got {last_intent!r}"
            )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return ScenarioResult(
        scenario_id=scenario.id,
        category=scenario.category,
        ok=not errors,
        errors=errors,
        turns=traces,
        elapsed_ms=elapsed_ms,
    )


def run_scenario_by_id(scenario_id: str) -> ScenarioResult:
    from tests.corpus.generate import generate_scenarios

    for scenario in generate_scenarios():
        if scenario.id == scenario_id:
            return run_scenario(scenario)
    return ScenarioResult(
        scenario_id=scenario_id,
        category="missing",
        ok=False,
        errors=[f"unknown scenario id: {scenario_id}"],
    )
