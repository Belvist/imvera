"""Map validated SemanticPayload to UserInterpretation for Planner."""

from __future__ import annotations

from packages.contracts.enums import AnswerJudgement, ConsentState, DialogueAct
from packages.contracts.interpretation import FactCandidate
from packages.contracts.semantic import SemanticPayload, evidence_matches
from packages.dialogue.interpretation import UserInterpretation


def semantic_to_user_interpretation(
    raw_text: str,
    payload: SemanticPayload,
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

    if payload.consent_answer == "yes":
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.ANSWER,
            affirms=True,
            sets_consent=ConsentState.ACTIVE,
        )
    if payload.consent_answer == "no":
        return UserInterpretation(
            judgement=AnswerJudgement.DECLINE,
            dialogue_act=DialogueAct.ANSWER,
            declines=True,
            sets_consent=ConsentState.DECLINED,
        )

    if payload.user_question:
        return UserInterpretation(
            judgement=AnswerJudgement.SIDE_TOPIC,
            dialogue_act=DialogueAct.QUESTION,
            asks_who_are_you="кто" in payload.user_question.lower(),
        )

    candidates: list[FactCandidate] = []
    for fact in payload.facts:
        if not evidence_matches(raw_text, fact.evidence):
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

    if payload.risk_candidates:
        for risk in payload.risk_candidates:
            if risk.proposal == "dismiss" and evidence_matches(raw_text, risk.evidence):
                return UserInterpretation(
                    judgement=AnswerJudgement.VALID,
                    dialogue_act=DialogueAct.CORRECTION,
                    risk_false_alarm=True,
                )

    if candidates:
        primary = candidates[0]
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=(
                DialogueAct.CORRECTION
                if payload.dialogue_act == "correction"
                else DialogueAct.ANSWER
            ),
            affirms=True,
            fills_pending_slot=any(c.answers_pending for c in candidates),
            slot_value=primary.value,
            fact_candidates=candidates,
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
