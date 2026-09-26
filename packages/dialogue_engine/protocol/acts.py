"""Act effects from the protocol table (CDK Step 2).

Understand normalizes a turn to one closed act (ADR-021 lattice); this
module applies the YAML-declared clears/enqueues/forbids to EngineState.
Dialogue branches on acts + queue — never on lexical ifs in policy.
The lexical safety net (complaint_without_negation) stays belt-and-
suspenders underneath and is NOT consulted here.
"""

from __future__ import annotations


def normalize_act(state, user_text: str) -> str | None:
    """One closed act or None, from existing understanding outputs only.

    - DECLINE: explicit denial-of-concern (existing helper).
    - ISSUE_SITE: kernel/legacy issue mentions present.
    - WELLNESS_OK: positive polarity answer while wellness was asked.
    New Russian phrasings map to these acts via Understand (Step 3);
    never a new `if "phrase" in text` here or in policy.
    """
    from packages.dialogue_engine.check_path import is_explicit_concern_decline
    from packages.dialogue_engine.issue_mention_extract import (
        extract_issue_mentions,
    )

    text = (user_text or "").strip()
    if not text:
        return None
    if is_explicit_concern_decline(text) and _concern_probe_open(state):
        # DECLINE declines something actually open — never a bare
        # "Хорошо." to a wellness question (that is WELLNESS_OK territory).
        return "DECLINE"
    try:
        mentions = extract_issue_mentions(text)
    except Exception:
        mentions = ()
    if mentions:
        return "ISSUE_SITE"
    delivered = state.delivered_question
    if delivered is not None and (delivered.slot or delivered.intent or "") in (
        "wellness",
        "check_wellness",
        "opening_wellness",
        "probe_wellness",
    ):
        record = state.slot_records.get("wellness")
        if record is not None and getattr(record, "polarity", None) == "positive":
            return "WELLNESS_OK"
    return None


def _concern_probe_open(state) -> bool:
    delivered = state.delivered_question
    if delivered is not None and (delivered.intent or "") in (
        "probe_concern",
        "probe_concern_options",
    ):
        return True
    if getattr(state, "probe_phase", None) == "concern":
        return True
    return int(getattr(state, "concern_probe_count", 0) or 0) > 0


def apply_act_effects(state, act: str) -> None:
    """Apply PROTOCOL["acts"][act] clears/enqueues/forbids to state."""
    from packages.dialogue_engine.protocol import ACTS

    spec = ACTS.get(act)
    if not spec:
        return
    for probe in spec.get("forbids", []) or []:
        if probe not in state.forbidden_actions:
            state.forbidden_actions.append(probe)
    for need in spec.get("enqueues", []) or []:
        if need not in state.queued_needs:
            state.queued_needs.append(need)
    for cleared in spec.get("clears", []) or []:
        if cleared == "open_probe" and state.probe_phase == "concern":
            state.probe_phase = None
        state.queued_needs = [n for n in state.queued_needs if n != cleared]
    state.bump_revision()


def consume_need(state, need: str) -> None:
    if need in state.queued_needs:
        state.queued_needs.remove(need)
        state.bump_revision()


def is_forbidden(state, probe: str) -> bool:
    return probe in state.forbidden_actions


def lift_forbids(state, probes: tuple[str, ...] = ("concern_probe", "pain_site_probe")) -> None:
    """Restated complaint lifts the DECLINE forbids (re-probe allowed)."""
    left = [p for p in state.forbidden_actions if p not in probes]
    if len(left) != len(state.forbidden_actions):
        state.forbidden_actions = left
        state.bump_revision()
