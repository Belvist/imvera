"""Single voice/text semantic path: validate → policy → interpretation (spec §8–9)."""

from __future__ import annotations

from packages.contracts.semantic import ActiveQuestionKind, SemanticPayload
from packages.dialogue.answer_policy import AnswerPolicy
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.semantic_bridge import semantic_to_user_interpretation
from packages.dialogue.semantic_validator import SemanticValidator, ValidatedSemantic
from packages.dialogue.state import DialogueState


def adapt_semantic_turn(
    raw_text: str,
    payload: SemanticPayload,
    *,
    state: DialogueState,
    active_question_kind: ActiveQuestionKind = "none",
    pending_slot: str | None = None,
) -> tuple[UserInterpretation, ValidatedSemantic]:
    """Validate and bind meaning before Planner sees it."""
    slot = pending_slot if pending_slot is not None else state.pending_slot
    delivered = state.pending_question_delivered

    validated = SemanticValidator.validate(
        raw_text,
        payload,
        active_question_kind=active_question_kind,
        pending_slot=slot,
        question_delivered=delivered,
    )
    policy_payload = AnswerPolicy.apply(
        validated.payload,
        raw_text,
        active_question_kind=active_question_kind,
        question_delivered=delivered,
    )
    if policy_payload != validated.payload:
        validated = ValidatedSemantic(
            payload=policy_payload,
            rejected_facts=validated.rejected_facts,
            reason_codes=list(validated.reason_codes) + ["answer_policy_adjusted"],
            consent_evidence_ok=validated.consent_evidence_ok,
            control_evidence_ok=validated.control_evidence_ok,
        )

    interp = semantic_to_user_interpretation(
        raw_text,
        validated.payload,
        active_question_kind=active_question_kind,
        pending_slot=slot,
    )
    return interp, validated
