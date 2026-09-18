"""Engine-native persistence projection — parity harness (ADR-019).

Builds the persisted `CallResultSnapshot` contract from `EngineState` alone,
without the legacy `DialogueState` mirror. Owner decision (b): the
legacy-compatible surface (`facts`, `fact_quotes`) is preserved verbatim;
rich engine evidence (`SlotValue.source_text`, polarity, observations,
`mission_result.evidence`) travels alongside and is never substituted into
the legacy surface.

Transitional exclusions (owned by `DialogueTransitionStore`, compared
separately, never silently dropped): `metadata.dialogue_state`,
`metadata.state_version`, `metadata.action_outbox`, `metadata.pending_action`.

`legacy_public_status` is a pass-through input until status ownership
migrates — it is not derived from the mirror here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from packages.contracts.core import CallResultSnapshot, TerminationReason
from packages.contracts.enums import SlotStatus
from packages.contracts.mandatory import PILOT_MANDATORY_CHECKS
from packages.dialogue_engine.check_path import build_call_metadata
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.mission_result import (
    build_call_outcomes,
    build_mission_result,
)

# Metadata keys owned by the transition store — excluded from parity by design.
STORE_OWNED_METADATA_KEYS = frozenset(
    {
        "dialogue_state",
        "state_version",
        "action_outbox",
        "pending_action",
    }
)


def project_call_result(
    engine: DialogueEngine,
    *,
    call_id: str,
    family_id: str,
    elder_display_name: str,
    observation_ids: list[str],
    mission_is_daily_check: bool,
    legacy_public_status: str | None = None,
    base_metadata: Mapping[str, Any] | None = None,
) -> CallResultSnapshot:
    """Project the persisted snapshot contract from engine state only.

    Starts from `base_metadata` (existing snapshot metadata) and overwrites
    engine-owned keys only, so store-owned/unknown keys survive on backends
    that replace metadata wholesale (Postgres) as well as merging ones.
    """
    state = engine.state
    facts: dict[str, str] = {}
    quotes: dict[str, str] = {}
    for slot, status in state.slots.items():
        if status == SlotStatus.FILLED and slot in state.slot_values:
            # Decision (b): verbatim legacy-compatible surface.
            val = state.slot_values[slot]
            facts[slot] = val
            quotes[slot] = val

    metadata: dict[str, Any] = dict(base_metadata) if base_metadata else {}
    metadata["elder_display_name"] = elder_display_name
    metadata.update(build_call_metadata(state))
    mission_result = build_mission_result(state)
    outcomes = build_call_outcomes(
        state,
        mission_result=mission_result,
        legacy_public_status=legacy_public_status,
    )
    metadata["mission_result"] = mission_result.model_dump(mode="json")
    metadata["outcomes"] = outcomes.model_dump(mode="json")
    # Project custom goal answers into facts for older readers
    # (non-authoritative) — same as the legacy snapshot path.
    for goal in mission_result.goals:
        if goal.value is not None:
            facts[goal.goal_id] = goal.value
            if goal.evidence:
                quotes[goal.goal_id] = goal.evidence[0]

    if state.call_closed:
        call_ended = True
        termination_reason = (
            TerminationReason.COMPLETED
            if state.closing_reason == "goodbye"
            else TerminationReason.PARTIAL
        )
    else:
        call_ended = False
        termination_reason = None

    if mission_is_daily_check:
        # Replicates the legacy rule exactly: sync_to_legacy marks a check
        # only for FILLED slots present in slot_values, so identity/consent/
        # can_talk stay open and partial is True. Preserved quirk, not a fix.
        remaining = [
            key
            for key in PILOT_MANDATORY_CHECKS
            if not (
                state.slots.get(key) == SlotStatus.FILLED and key in state.slot_values
            )
        ]
        partial = bool(remaining)
    else:
        partial = mission_result.status != "COMPLETED" if mission_result else True

    return CallResultSnapshot(
        call_id=call_id,
        family_id=family_id,
        fsm_state=state.fsm_state,
        facts=facts,
        fact_quotes=quotes,
        observations=list(observation_ids),
        partial=partial,
        call_ended=call_ended,
        termination_reason=termination_reason,
        metadata=metadata,
        mission_result=mission_result,
        outcomes=outcomes,
    )
