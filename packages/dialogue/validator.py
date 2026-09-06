"""Validator — whether proposed speech may be spoken."""

from packages.contracts.turn import TurnProposal, ValidatedTurn

_MAX_CHARS = 200
_FORBIDDEN_PROMISES = ("я вызову", "я позвоню", "отправлю скорую")


class Validator:
    @staticmethod
    def validate(proposal: TurnProposal) -> ValidatedTurn:
        speech = proposal.speech.strip()
        notes: list[str] = []

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

        if proposal.fsm_state.name in ("SUMMARY", "GOODBYE") and proposal.mandatory_remaining:
            return ValidatedTurn(
                turn_id=proposal.turn_id,
                generation_id=proposal.generation_id,
                speech=speech,
                intent=proposal.intent,
                fsm_state=proposal.fsm_state,
                allowed=False,
                validator_notes="mandatory checks incomplete",
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
