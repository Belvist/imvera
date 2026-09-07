"""Map validated SemanticPayload to UserInterpretation for Planner."""

from __future__ import annotations

from packages.contracts.enums import AnswerJudgement, ConsentState, DialogueAct
from packages.contracts.interpretation import FactCandidate
from packages.contracts.semantic import ActiveQuestionKind, SemanticPayload, evidence_matches
from packages.dialogue.interpretation import UserInterpretation

_CURRENT_SCOPES = frozenset({"now", "today"})


def _consent_evidence_ok(raw_text: str, payload: SemanticPayload) -> bool:
    if payload.consent_evidence is None:
        return False
    return evidence_matches(raw_text, payload.consent_evidence)


def _fact_applies_to_pending(
    fact_field: str,
    temporal_scope: str,
    *,
    pending_slot: str | None,
) -> bool:
    if temporal_scope not in _CURRENT_SCOPES and temporal_scope != "unknown":
        if pending_slot and fact_field == pending_slot:
            return False
        if fact_field in ("wellness", "mood") and temporal_scope == "past":
            return False
    return True


def _extract_fact_candidates(
    raw_text: str,
    payload: SemanticPayload,
    *,
    pending_slot: str | None = None,
) -> list[FactCandidate]:
    candidates: list[FactCandidate] = []
    for fact in payload.facts:
        if not evidence_matches(raw_text, fact.evidence):
            continue
        if fact.subject in ("other", "unknown"):
            continue
        if not _fact_applies_to_pending(
            fact.field,
            fact.temporal_scope,
            pending_slot=pending_slot,
        ):
            continue
        candidates.append(
            FactCandidate(
                field=fact.field,
                value=fact.value,
                subject="elder" if fact.subject == "speaker" else fact.subject,
                negated=fact.negated,
                source_quote=fact.evidence.quote,
                answers_pending=payload.answers_pending_question,
            )
        )
    return candidates


def semantic_to_user_interpretation(
    raw_text: str,
    payload: SemanticPayload,
    *,
    active_question_kind: ActiveQuestionKind = "none",
    pending_slot: str | None = None,
) -> UserInterpretation:
    if payload.control == "stop_call":
        return UserInterpretation(
            judgement=AnswerJudgement.SIDE_TOPIC,
            dialogue_act=DialogueAct.STOP_CALL,
            requests_goodbye=True,
        )
    if payload.control == "revoke_consent":
        return UserInterpretation(
            judgement=AnswerJudgement.DECLINE,
            dialogue_act=DialogueAct.REVOKE_CONSENT,
            declines=True,
            revoke_consent=True,
            sets_consent=ConsentState.DECLINED,
        )
    if payload.control == "wrong_person":
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.WRONG_PERSON,
            wrong_person=True,
        )
    if payload.control == "defer":
        return UserInterpretation(
            judgement=AnswerJudgement.SIDE_TOPIC,
            dialogue_act=DialogueAct.DEFER,
            defers_call=True,
        )
    if payload.control == "pause":
        return UserInterpretation(
            judgement=AnswerJudgement.SIDE_TOPIC,
            dialogue_act=DialogueAct.PAUSE,
            pause_requested=True,
        )

    fact_candidates = _extract_fact_candidates(
        raw_text, payload, pending_slot=pending_slot
    )

    if active_question_kind == "goodbye":
        if payload.consent_answer == "no" and _consent_evidence_ok(raw_text, payload):
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.ANSWER,
                declines=True,
                declines_goodbye=True,
                fact_candidates=fact_candidates,
            )
        if payload.consent_answer == "yes" and _consent_evidence_ok(raw_text, payload):
            return UserInterpretation(
                judgement=AnswerJudgement.VALID,
                dialogue_act=DialogueAct.ANSWER,
                affirms=True,
                confirms_goodbye=True,
                fact_candidates=fact_candidates,
            )
        if payload.answers_pending_question and _consent_evidence_ok(raw_text, payload):
            return UserInterpretation(
                judgement=AnswerJudgement.VALID,
                dialogue_act=DialogueAct.ANSWER,
                affirms=True,
                confirms_goodbye=True,
                fact_candidates=fact_candidates,
            )

    if active_question_kind == "identity":
        if payload.consent_answer == "no":
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.ANSWER,
                declines=True,
                fact_candidates=fact_candidates,
            )
        if payload.consent_answer == "yes" and _consent_evidence_ok(raw_text, payload):
            return UserInterpretation(
                judgement=AnswerJudgement.VALID,
                dialogue_act=DialogueAct.ANSWER,
                affirms=True,
                confirms_identity=True,
                fact_candidates=fact_candidates,
            )

    if active_question_kind == "consent":
        if payload.consent_answer == "no" and _consent_evidence_ok(raw_text, payload):
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.ANSWER,
                declines=True,
                sets_consent=ConsentState.DECLINED,
                fact_candidates=fact_candidates,
            )
        if payload.consent_answer == "yes" and _consent_evidence_ok(raw_text, payload):
            return UserInterpretation(
                judgement=AnswerJudgement.VALID,
                dialogue_act=DialogueAct.ANSWER,
                affirms=True,
                sets_consent=ConsentState.ACTIVE,
                fact_candidates=fact_candidates,
            )

    if active_question_kind == "can_talk":
        if payload.consent_answer == "no" and _consent_evidence_ok(raw_text, payload):
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.ANSWER,
                declines=True,
                fact_candidates=fact_candidates,
            )
        if payload.consent_answer == "yes" and _consent_evidence_ok(raw_text, payload):
            return UserInterpretation(
                judgement=AnswerJudgement.VALID,
                dialogue_act=DialogueAct.ANSWER,
                affirms=True,
                confirms_can_talk=True,
                fact_candidates=fact_candidates,
            )
        if (
            payload.dialogue_act == "answer"
            and payload.answers_pending_question
            and _consent_evidence_ok(raw_text, payload)
        ):
            return UserInterpretation(
                judgement=AnswerJudgement.VALID,
                dialogue_act=DialogueAct.ANSWER,
                affirms=True,
                confirms_can_talk=True,
                fact_candidates=fact_candidates,
            )

    if payload.user_question:
        lowered = payload.user_question.lower()
        return UserInterpretation(
            judgement=AnswerJudgement.SIDE_TOPIC,
            dialogue_act=DialogueAct.QUESTION,
            asks_who_are_you="кто" in lowered or "зачем" in lowered,
            fact_candidates=fact_candidates,
        )

    if payload.risk_candidates:
        for risk in payload.risk_candidates:
            if risk.proposal == "dismiss" and evidence_matches(raw_text, risk.evidence):
                return UserInterpretation(
                    judgement=AnswerJudgement.VALID,
                    dialogue_act=DialogueAct.CORRECTION,
                    risk_false_alarm=True,
                    fact_candidates=fact_candidates,
                )

    if fact_candidates:
        primary = fact_candidates[0]
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=(
                DialogueAct.CORRECTION
                if payload.dialogue_act == "correction"
                else DialogueAct.ANSWER
            ),
            affirms=True,
            fills_pending_slot=any(c.answers_pending for c in fact_candidates),
            slot_value=primary.value,
            fact_candidates=fact_candidates,
        )

    if payload.dialogue_act == "repeat":
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.REPEAT,
            requests_repeat=True,
        )

    if payload.dialogue_act == "backchannel":
        return UserInterpretation(
            judgement=AnswerJudgement.BACKCHANNEL,
            dialogue_act=DialogueAct.BACKCHANNEL,
        )

    if payload.needs_clarification or payload.dialogue_act == "unclear":
        return UserInterpretation(
            judgement=AnswerJudgement.UNCLEAR,
            dialogue_act=DialogueAct.UNCLEAR,
        )

    return UserInterpretation(
        judgement=AnswerJudgement.UNCLEAR,
        dialogue_act=DialogueAct.UNCLEAR,
    )
