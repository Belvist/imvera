"""Validator — whether proposed speech may be spoken."""

from packages.contracts.turn import TurnProposal, ValidatedTurn

_MAX_CHARS = 200
_FORBIDDEN_PROMISES = (
    "я вызову",
    "я позвоню",
    "отправлю скорую",
    "я помогу",
    "сейчас вас спасут",
    "всё будет хорошо",
    "теперь вы в безопасности",
    "нужна ли вам помощь",
)
_FORBIDDEN_UNCONFIRMED = (
    "семья уже получила",
    "родственники уже получили",
    "уведомление доставлено",
)


class Validator:
    @staticmethod
    def validate(proposal: TurnProposal) -> ValidatedTurn:
        speech = proposal.speech.strip()
        notes: list[str] = []

        if not speech and proposal.intent == "terminal_noop":
            return ValidatedTurn(
                turn_id=proposal.turn_id,
                generation_id=proposal.generation_id,
                speech=speech,
                intent=proposal.intent,
                fsm_state=proposal.fsm_state,
                allowed=True,
                validator_notes="terminal noop",
            )

        if not speech and proposal.intent == "wait_for_continuation":
            return ValidatedTurn(
                turn_id=proposal.turn_id,
                generation_id=proposal.generation_id,
                speech=speech,
                intent=proposal.intent,
                fsm_state=proposal.fsm_state,
                allowed=True,
                validator_notes="answer wait continuation",
            )

        if not speech:
            return ValidatedTurn(
                turn_id=proposal.turn_id,
                generation_id=proposal.generation_id,
                speech=speech,
                intent=proposal.intent,
                fsm_state=proposal.fsm_state,
                allowed=False,
                validator_notes="empty speech",
            )

        if len(speech) > _MAX_CHARS:
            notes.append("truncated")
            speech = speech[:_MAX_CHARS]

        lower = speech.lower()

        if proposal.intent == "reflect_report":
            for praise in ("отлично", "замечательно", "как настроение", "хорошо!"):
                if praise in lower:
                    return ValidatedTurn(
                        turn_id=proposal.turn_id,
                        generation_id=proposal.generation_id,
                        speech=speech,
                        intent=proposal.intent,
                        fsm_state=proposal.fsm_state,
                        allowed=False,
                        validator_notes=f"praise_on_complaint: {praise}",
                    )
            if "?" in speech:
                return ValidatedTurn(
                    turn_id=proposal.turn_id,
                    generation_id=proposal.generation_id,
                    speech=speech,
                    intent=proposal.intent,
                    fsm_state=proposal.fsm_state,
                    allowed=False,
                    validator_notes="reflect_report must not add questions",
                )

        for phrase in _FORBIDDEN_PROMISES:
            if phrase in lower:
                return ValidatedTurn(
                    turn_id=proposal.turn_id,
                    generation_id=proposal.generation_id,
                    speech=speech,
                    intent=proposal.intent,
                    fsm_state=proposal.fsm_state,
                    allowed=False,
                    validator_notes=f"forbidden promise: {phrase}",
                )

        for phrase in _FORBIDDEN_UNCONFIRMED:
            if phrase in lower:
                return ValidatedTurn(
                    turn_id=proposal.turn_id,
                    generation_id=proposal.generation_id,
                    speech=speech,
                    intent=proposal.intent,
                    fsm_state=proposal.fsm_state,
                    allowed=False,
                    validator_notes=f"unconfirmed delivery claim: {phrase}",
                )

        if proposal.fsm_state.name in ("SUMMARY", "GOODBYE") and proposal.mandatory_remaining:
            if proposal.intent not in (
                "partial_unresolved_close",
                "goodbye_final",
                "consent_declined_final",
                "wrong_person_final",
                "defer_call_final",
            ):
                return ValidatedTurn(
                    turn_id=proposal.turn_id,
                    generation_id=proposal.generation_id,
                    speech=speech,
                    intent=proposal.intent,
                    fsm_state=proposal.fsm_state,
                    allowed=False,
                    validator_notes="mandatory checks incomplete",
                )

        if (
            proposal.intent == "partial_unresolved_close"
            and proposal.fsm_state.name == "FINAL_CLASSIFICATION"
        ):
            return ValidatedTurn(
                turn_id=proposal.turn_id,
                generation_id=proposal.generation_id,
                speech=speech,
                intent=proposal.intent,
                fsm_state=proposal.fsm_state,
                allowed=True,
                validator_notes="partial close allowed",
            )

        return ValidatedTurn(
            turn_id=proposal.turn_id,
            generation_id=proposal.generation_id,
            speech=speech,
            intent=proposal.intent,
            fsm_state=proposal.fsm_state,
            allowed=True,
            validator_notes="; ".join(notes) if notes else None,
        )
