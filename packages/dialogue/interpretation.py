"""Structured interpretation of elder speech — not raw VALID from STT."""

import re

from pydantic import BaseModel

from packages.contracts.enums import AnswerJudgement, ConsentState, FsmState
from packages.dialogue.state import DialogueState

_AFFIRM = re.compile(
    r"^(да|ага|угу|верно|согласен|согласна|конечно|хорошо|ладно|это\s+я|я\s+это)",
    re.I,
)
_DENY = re.compile(
    r"(^нет\b|не\s+соглас|не\s+хочу|не\s+надо|не\s+звоните|не\s+я\b|это\s+не\s+я)",
    re.I,
)


class UserInterpretation(BaseModel):
    judgement: AnswerJudgement
    affirms: bool = False
    declines: bool = False
    fills_pending_slot: bool = False
    sets_consent: ConsentState | None = None
    confirms_identity: bool = False
    confirms_can_talk: bool = False


def interpret_user_turn(state: DialogueState, user_text: str) -> UserInterpretation:
    """Derive structured meaning from transcript + dialogue context."""
    text = user_text.strip()
    if not text:
        return UserInterpretation(judgement=AnswerJudgement.NO_ANSWER)

    normalized = text.lower()

    if _DENY.search(normalized):
        if state.fsm_state == FsmState.CHECK_CONSENT:
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                declines=True,
                sets_consent=ConsentState.DECLINED,
            )
        if state.fsm_state == FsmState.IDENTIFY_PERSON:
            return UserInterpretation(judgement=AnswerJudgement.DECLINE, declines=True)
        if state.fsm_state == FsmState.CHECK_CAN_TALK:
            return UserInterpretation(judgement=AnswerJudgement.DECLINE, declines=True)
        if state.pending_slot:
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                declines=True,
            )

    if state.fsm_state == FsmState.IDENTIFY_PERSON and _AFFIRM.search(normalized):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            affirms=True,
            confirms_identity=True,
        )

    if state.fsm_state == FsmState.CHECK_CONSENT and _AFFIRM.search(normalized):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            affirms=True,
            sets_consent=ConsentState.ACTIVE,
        )

    if state.fsm_state == FsmState.CHECK_CAN_TALK and _AFFIRM.search(normalized):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            affirms=True,
            confirms_can_talk=True,
        )

    if state.fsm_state == FsmState.GREETING and state.greeted:
        return UserInterpretation(judgement=AnswerJudgement.BACKCHANNEL)

    if state.pending_slot and len(normalized) >= 2:
        if normalized in ("ага", "угу", "алло", "да"):
            return UserInterpretation(judgement=AnswerJudgement.BACKCHANNEL)
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            affirms=True,
            fills_pending_slot=True,
        )

    if state.fsm_state in (
        FsmState.IDENTIFY_PERSON,
        FsmState.CHECK_CONSENT,
        FsmState.CHECK_CAN_TALK,
    ):
        return UserInterpretation(judgement=AnswerJudgement.UNCLEAR)

    return UserInterpretation(judgement=AnswerJudgement.SIDE_TOPIC)
