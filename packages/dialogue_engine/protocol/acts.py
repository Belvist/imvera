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

    Priority is explicit (documented): DECLINE > SIDE_TOPIC (false-world
    non-complaint frames: narrative/dream, other-person, joke, past-resolved,
    side chatter) > ISSUE_SITE > ISSUE_SEVERITY_ANSWER >
    WELLNESS_SO_SO > WELLNESS_OK.
    New Russian phrasings map to these acts via Understand (fact
    extractors, polarity, mentions); never a new `if "phrase" in text`
    here or in policy.
    """
    from packages.dialogue_engine.check_path import is_explicit_concern_decline
    from packages.dialogue_engine.issue_mention_extract import (
        extract_goal_facts,
        extract_issue_mentions,
    )

    text = (user_text or "").strip()
    if not text:
        return None
    if declines_open_concern_probe(state, text):
        return "DECLINE"
    if is_explicit_concern_decline(text) and _decline_targets_open(state):
        # Soft branch: denial with no probe open but wellness declinable
        # (gate flow) — same act, same YAML effects.
        return "DECLINE"
    from packages.dialogue_engine.check_path import (
        is_narrative_fiction_frame,
        is_side_topic_chatter,
        suppress_health_issues_for_non_complaint_frame,
    )

    # False-world frames → SIDE_TOPIC, never ISSUE_SITE (even if a legacy
    # extractor still surfaces a body verb). Real speaker pivots fall through.
    if suppress_health_issues_for_non_complaint_frame(text):
        return "SIDE_TOPIC"

    try:
        mentions = extract_issue_mentions(text)
    except Exception:
        mentions = ()
    if mentions:
        return "ISSUE_SITE"
    from packages.dialogue_engine.check_path import _PRESENT_ACTIVE_COMPLAINT_PIVOT

    if _PRESENT_ACTIVE_COMPLAINT_PIVOT.search(text):
        # Siteless present-tense speaker complaint: live complaint needing
        # the concern pipeline, not silence.
        return "ISSUE_SITE"
    from packages.dialogue_engine.check_path import (
        _PRESENT_ACTIVE_COMPLAINT_PIVOT,
    )

    # Siteless present-tense speaker complaint («а сейчас у меня болит»):
    # same ISSUE_SITE act via the existing pivot detector, not a new regex.
    if _PRESENT_ACTIVE_COMPLAINT_PIVOT.search(text):
        return "ISSUE_SITE"
    if is_narrative_fiction_frame(text) or is_side_topic_chatter(text):
        # Frame/chatter with empty mentions — mark SIDE_TOPIC so policy
        # does not treat the turn as silence / invent a concern.
        return "SIDE_TOPIC"
    if _is_severity_answer(state, text):
        return "ISSUE_SEVERITY_ANSWER"
    try:
        fields = {
            (f.field, f.value)
            for f in extract_goal_facts(text, answer_slot="wellness")
        }
    except Exception:
        fields = set()
    if ("wellness", "uncertain") in fields:
        return "WELLNESS_SO_SO"
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
        if ("wellness", "positive") in fields:
            return "WELLNESS_OK"
    return None


def _is_severity_answer(state, text: str) -> bool:
    """Answer carrying onset/severity content while such a probe is open."""
    delivered = state.delivered_question
    intent = (getattr(delivered, "intent", "") or "") if delivered else ""
    if not any(k in intent for k in ("severity", "duration", "onset")):
        if (state.probe_phase or "") not in ("severity", "duration"):
            return False
    try:
        from packages.dialogue_engine.issue_memory import (
            extract_grounded_onset_value,
            extract_grounded_severity_value,
        )

        return bool(
            extract_grounded_severity_value(text)
            or extract_grounded_onset_value(text)
        )
    except Exception:
        return False


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


def _is_bare_positive_ok(text: str) -> bool:
    from packages.dialogue_engine.fast_interpreter import _POSITIVE

    return bool(_POSITIVE.match((text or "").strip()))


def declines_open_concern_probe(state, text: str) -> bool:
    """Decline of an OPEN concern probe: denial shapes OR bare positive.

    "Нормально." to "Что беспокоит?" means "I'm fine" — accept at once.
    Bare positives elsewhere are NOT declines (WELLNESS_OK territory).
    """
    from packages.dialogue_engine.check_path import is_explicit_concern_decline

    if not _concern_probe_open(state):
        return False
    t = (text or "").strip()
    if is_explicit_concern_decline(t):
        return True
    return _is_bare_positive_ok(t)


def _decline_targets_open(state) -> bool:
    """Something declinable is open: concern probe, or soft wellness branch.

    Soft branch = no grounded complaint, no specific probe running.
    No FILLED check: explicit denial with filled wellness still declines
    further probing (gate). Bare positives never reach here anyway
    (helper excludes them) — so this gate cannot misfire on "Хорошо.".
    """
    if _concern_probe_open(state):
        return True
    if (state.wellness_concern or "").strip():
        return False
    if (state.probe_phase or "") in ("duration", "severity", "pain_night"):
        return False
    return True


def apply_act_effects(state, act: str) -> None:
    """Apply PROTOCOL["acts"][act] clears/enqueues/forbids to state."""
    from packages.dialogue_engine.protocol import ACTS

    spec = ACTS.get(act)
    if not spec:
        return
    try:
        state.last_protocol_act = act
    except Exception:
        pass
    for probe in spec.get("forbids", []) or []:
        if probe not in state.forbidden_actions:
            state.forbidden_actions.append(probe)
    for need in spec.get("enqueues", []) or []:
        if need not in state.queued_needs:
            state.queued_needs.append(need)
    for cleared in spec.get("clears", []) or []:
        if cleared == "open_probe" and state.probe_phase == "concern":
            state.probe_phase = None
        if cleared == "severity":
            consume_need(state, "severity")
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
