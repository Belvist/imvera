"""Deterministic grounding for mission GoalAnswerCandidate before EngineState mutation.

MODEL/provider output = candidate. Engine validation = authority.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from packages.dialogue_engine.mission import CallMission, GoalAnswerCandidate, definition_by_id

if TYPE_CHECKING:
    pass


def _norm_space(text: str) -> str:
    return " ".join((text or "").casefold().split())


def evidence_grounded_in_utterance(evidence: str, utterance: str) -> bool:
    """Evidence must appear as a contiguous span in the user utterance."""
    ev = _norm_space(evidence)
    ut = _norm_space(utterance)
    if not ev or not ut:
        return False
    if ev in ut:
        return True
    # Allow minor punctuation drift: strip non-word from both for secondary check.
    ev2 = re.sub(r"[^\wа-яё]+", " ", ev, flags=re.I)
    ut2 = re.sub(r"[^\wа-яё]+", " ", ut, flags=re.I)
    ev2 = " ".join(ev2.split())
    ut2 = " ".join(ut2.split())
    return bool(ev2) and ev2 in ut2


def validate_goal_answer_candidate(
    candidate: GoalAnswerCandidate,
    *,
    mission: CallMission,
    utterance: str,
) -> tuple[bool, str]:
    """Return (ok, reason). Invalid candidates must not SATISFY goals."""
    if not candidate.goal_id:
        return False, "missing_goal_id"
    gdef = definition_by_id(mission, candidate.goal_id)
    if gdef is None:
        return False, "unknown_goal_id"

    value = str(candidate.value).strip()
    if not value:
        return False, "empty_value"

    if gdef.answer_type in {"enum", "bool"}:
        allowed = tuple(gdef.allowed_values) or ("yes", "no", "unknown")
        if value not in allowed:
            return False, "value_not_in_allowed_values"
    elif gdef.answer_type == "free_text":
        if len(value) < 1:
            return False, "empty_free_text"
    else:
        return False, "unsupported_answer_type"

    evidence = (candidate.evidence or "").strip()
    if not evidence:
        return False, "missing_evidence"
    if not evidence_grounded_in_utterance(evidence, utterance):
        return False, "evidence_not_grounded"

    if candidate.confidence < 0.0 or candidate.confidence > 1.0:
        return False, "invalid_confidence"

    return True, "ok"


def validate_goal_disposition_candidate(
    candidate,
    *,
    mission: CallMission,
    utterance: str,
) -> tuple[bool, str]:
    from packages.dialogue_engine.mission import GoalDispositionCandidate

    if not isinstance(candidate, GoalDispositionCandidate):
        return False, "not_disposition"
    if not candidate.goal_id:
        return False, "missing_goal_id"
    if definition_by_id(mission, candidate.goal_id) is None:
        return False, "unknown_goal_id"
    if candidate.disposition not in {"declined", "not_applicable", "unclear"}:
        return False, "invalid_disposition"
    evidence = (candidate.evidence or "").strip()
    if not evidence:
        return False, "missing_evidence"
    if not evidence_grounded_in_utterance(evidence, utterance):
        return False, "evidence_not_grounded"
    return True, "ok"


def filter_grounded_goal_answers(
    candidates: tuple[GoalAnswerCandidate, ...] | list[GoalAnswerCandidate],
    *,
    mission: CallMission,
    utterance: str,
    existing_satisfied: set[str] | None = None,
) -> tuple[GoalAnswerCandidate, ...]:
    """Keep only engine-authoritative candidates. Multiple answers allowed."""
    out: list[GoalAnswerCandidate] = []
    seen: set[str] = set()
    satisfied = existing_satisfied or set()
    for cand in candidates:
        ok, _reason = validate_goal_answer_candidate(
            cand, mission=mission, utterance=utterance
        )
        if not ok:
            continue
        if cand.goal_id in satisfied and not cand.is_correction:
            continue
        if cand.goal_id in seen and not cand.is_correction:
            continue
        seen.add(cand.goal_id)
        out.append(cand)
    return tuple(out)


def filter_grounded_dispositions(
    candidates: tuple | list,
    *,
    mission: CallMission,
    utterance: str,
) -> tuple:
    out = []
    seen: set[str] = set()
    for cand in candidates or ():
        ok, _ = validate_goal_disposition_candidate(
            cand, mission=mission, utterance=utterance
        )
        if not ok:
            continue
        if cand.goal_id in seen:
            continue
        seen.add(cand.goal_id)
        out.append(cand)
    return tuple(out)
