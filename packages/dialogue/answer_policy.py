"""Conservative answer binding — backchannel and consent guards (spec §7)."""

from __future__ import annotations

import re

from packages.contracts.semantic import ActiveQuestionKind, Evidence, SemanticPayload

_BACKCHANNEL_ONLY = re.compile(
    r"^\s*(ага|угу|мгм|м-м|мм|алло)\s*[.!?…]*\s*$",
    re.I,
)
_AFFIRM_ONLY = re.compile(r"^\s*(да|нет)\s*[.!?…]*\s*$", re.I)


def _affirm_evidence(text: str) -> Evidence:
    stripped = text.strip()
    return Evidence(start=0, end=len(stripped), quote=stripped)


class AnswerPolicy:
    @staticmethod
    def apply(
        payload: SemanticPayload,
        raw_text: str,
        *,
        active_question_kind: ActiveQuestionKind,
        question_delivered: bool,
    ) -> SemanticPayload:
        text = raw_text.strip()
        if not text:
            return payload

        if _BACKCHANNEL_ONLY.match(text):
            return payload.model_copy(
                update={
                    "dialogue_act": "backchannel",
                    "answers_pending_question": False,
                    "consent_answer": "not_applicable",
                    "facts": (),
                }
            )

        if payload.dialogue_act == "backchannel" and payload.facts:
            return payload.model_copy(update={"dialogue_act": "answer"})

        if _AFFIRM_ONLY.match(text):
            if not question_delivered or active_question_kind == "none":
                return payload.model_copy(
                    update={
                        "dialogue_act": "unclear",
                        "answers_pending_question": False,
                        "consent_answer": "unclear",
                        "facts": (),
                    }
                )
            lowered = text.strip().lower()
            is_yes = lowered.startswith("да")
            is_no = lowered.startswith("нет")
            if active_question_kind in ("identity", "consent", "can_talk") and (is_yes or is_no):
                return payload.model_copy(
                    update={
                        "dialogue_act": "answer",
                        "consent_answer": "yes" if is_yes else "no",
                        "consent_evidence": _affirm_evidence(text),
                        "answers_pending_question": True,
                        "facts": (),
                    }
                )
            if active_question_kind == "consent" and payload.consent_answer == "yes":
                return payload
            if active_question_kind == "can_talk" and payload.consent_answer == "yes":
                return payload
            if active_question_kind == "identity" and payload.consent_answer == "yes":
                return payload.model_copy(
                    update={
                        "consent_evidence": payload.consent_evidence
                        or _affirm_evidence(text),
                    }
                )
            if active_question_kind == "slot" and payload.answers_pending_question:
                return payload

        if payload.consent_answer in ("yes", "no"):
            allowed = {
                "identity": active_question_kind == "identity",
                "consent": active_question_kind == "consent",
                "can_talk": active_question_kind == "can_talk",
                "slot": active_question_kind == "slot" and question_delivered,
            }
            if not allowed.get(active_question_kind, False):
                return payload.model_copy(
                    update={
                        "consent_answer": "not_applicable",
                        "answers_pending_question": False,
                    }
                )

        return payload
