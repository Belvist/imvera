"""Validate LLM semantic payload before state changes (spec §9)."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.contracts.semantic import (
    ActiveQuestionKind,
    Evidence,
    FactCandidate,
    SemanticPayload,
    evidence_matches,
)

_CURRENT_SCOPES = frozenset({"now", "today", "unknown"})


@dataclass(frozen=True)
class RejectedFact:
    fact: FactCandidate
    reason: str


@dataclass
class ValidatedSemantic:
    payload: SemanticPayload
    rejected_facts: list[RejectedFact] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    consent_evidence_ok: bool = False
    control_evidence_ok: bool = False


class SemanticValidator:
    @staticmethod
    def validate(
        raw_text: str,
        payload: SemanticPayload,
        *,
        active_question_kind: ActiveQuestionKind = "none",
        pending_slot: str | None = None,
        question_delivered: bool = False,
    ) -> ValidatedSemantic:
        reason_codes: list[str] = []
        rejected: list[RejectedFact] = []
        accepted_facts: list[FactCandidate] = []

        consent_ok = (
            payload.consent_evidence is not None
            and evidence_matches(raw_text, payload.consent_evidence)
        )
        control_ok = (
            payload.control_evidence is None
            or evidence_matches(raw_text, payload.control_evidence)
        )

        for fact in payload.facts:
            fact = SemanticValidator._normalize_fact_evidence(raw_text, fact)
            reject_reason = SemanticValidator._reject_fact_reason(
                raw_text,
                fact,
                pending_slot=pending_slot,
            )
            if reject_reason:
                rejected.append(RejectedFact(fact=fact, reason=reject_reason))
                reason_codes.append(reject_reason)
                continue
            accepted_facts.append(fact)

        safe_payload = payload.model_copy(update={"facts": tuple(accepted_facts)})

        if payload.answers_pending_question and not question_delivered:
            if active_question_kind in ("identity", "consent", "can_talk", "slot"):
                safe_payload = safe_payload.model_copy(
                    update={"answers_pending_question": False}
                )
                reason_codes.append("answer_without_delivered_question")

        if payload.consent_answer in ("yes", "no") and not consent_ok:
            safe_payload = safe_payload.model_copy(
                update={"consent_answer": "unclear", "answers_pending_question": False}
            )
            reason_codes.append("consent_without_evidence")

        if payload.control != "none" and not control_ok:
            safe_payload = safe_payload.model_copy(update={"control": "none"})
            reason_codes.append("control_without_evidence")

        return ValidatedSemantic(
            payload=safe_payload,
            rejected_facts=rejected,
            reason_codes=reason_codes,
            consent_evidence_ok=consent_ok,
            control_evidence_ok=control_ok,
        )

    @staticmethod
    def _normalize_fact_evidence(raw_text: str, fact: FactCandidate) -> FactCandidate:
        if evidence_matches(raw_text, fact.evidence):
            return fact
        for quote in (fact.evidence.quote.strip(), fact.value.strip()):
            if quote and quote in raw_text:
                start = raw_text.index(quote)
                end = start + len(quote)
                return fact.model_copy(
                    update={
                        "evidence": Evidence(
                            start=start,
                            end=end,
                            quote=raw_text[start:end],
                        )
                    }
                )
        return fact

    @staticmethod
    def _reject_fact_reason(
        raw_text: str,
        fact: FactCandidate,
        *,
        pending_slot: str | None,
    ) -> str | None:
        if not evidence_matches(raw_text, fact.evidence):
            return "evidence_span_mismatch"
        if fact.subject in ("other", "unknown"):
            return "subject_not_self"
        if fact.negated and fact.field in ("wellness", "mood"):
            return None
        if fact.temporal_scope == "past" and fact.field in ("wellness", "mood"):
            if pending_slot and fact.field == pending_slot:
                lowered = f"{fact.value} {fact.evidence.quote}".lower()
                if any(marker in lowered for marker in ("бол", "плох", "устал", "с утра", "сегодня")):
                    return None
                return "past_not_current_answer"
        if fact.temporal_scope not in _CURRENT_SCOPES and fact.field in (
            "wellness",
            "mood",
        ):
            if pending_slot and fact.field == pending_slot:
                return "temporal_not_current"
        if not fact.value.strip():
            return "empty_value"
        if not SemanticValidator._evidence_covers_value(raw_text, fact.evidence, fact.value):
            return "value_not_in_evidence"
        return None

    @staticmethod
    def _evidence_covers_value(raw_text: str, evidence: Evidence, value: str) -> bool:
        span = raw_text[evidence.start : evidence.end]
        normalized_value = value.strip().lower()
        normalized_span = span.strip().lower()
        if normalized_value in normalized_span or normalized_span in normalized_value:
            return True
        return normalized_value[:20] in normalized_span
