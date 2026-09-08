"""Semantic interpretation output — meaning only, no dialogue control."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from packages.dialogue_engine.context import SlotCandidate


class SemanticAct(StrEnum):
    ANSWER = "answer"
    REPAIR_REQUEST = "repair_request"
    UNCLEAR = "unclear"
    BACKCHANNEL = "backchannel"
    NO_ANSWER = "no_answer"
    GOODBYE_REQUEST = "goodbye_request"
    GOODBYE_CONFIRM = "goodbye_confirm"


class SemanticTurn(BaseModel):
    """Fast/LLM NLU result — reducer owns all FSM transitions."""

    act: SemanticAct
    answers_to: str | None = None
    slots: dict[str, SlotCandidate] = Field(default_factory=dict)
    target_slot: str | None = None
    polarity: str | None = None  # positive | negative | uncertain
    confidence: float = 0.0
    source_quote: str = ""
    value: str = ""
    correction: bool = False
    repair: bool = False
    backchannel: bool = False

    model_config = {"frozen": True}


def semantic_to_interpretation(semantic: SemanticTurn):
    """Convert SemanticTurn → legacy UserInterpretation for traces/contracts."""
    from packages.contracts.enums import AnswerJudgement, DialogueAct
    from packages.contracts.interpretation import FactCandidate
    from packages.dialogue.interpretation import UserInterpretation

    if semantic.act == SemanticAct.REPAIR_REQUEST:
        return UserInterpretation(
            judgement=AnswerJudgement.UNCLEAR,
            dialogue_act=DialogueAct.REPEAT,
            requests_repeat=True,
        )
    if semantic.act == SemanticAct.BACKCHANNEL:
        return UserInterpretation(
            judgement=AnswerJudgement.BACKCHANNEL,
            dialogue_act=DialogueAct.BACKCHANNEL,
        )
    if semantic.act == SemanticAct.ANSWER and (semantic.slots or semantic.target_slot):
        candidates = []
        if semantic.slots:
            for field, cand in semantic.slots.items():
                candidates.append(
                    FactCandidate(
                        field=field,
                        value=cand.value,
                        source_quote=semantic.source_quote,
                        answers_pending=field == semantic.answers_to,
                    )
                )
        elif semantic.target_slot:
            candidates.append(
                FactCandidate(
                    field=semantic.target_slot,
                    value=semantic.value or semantic.source_quote,
                    source_quote=semantic.source_quote,
                    answers_pending=True,
                )
            )
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.ANSWER,
            fills_pending_slot=True,
            slot_value=semantic.value or semantic.source_quote,
            fact_candidates=candidates,
        )
    if semantic.act == SemanticAct.GOODBYE_REQUEST:
        return UserInterpretation(
            judgement=AnswerJudgement.UNCLEAR,
            dialogue_act=DialogueAct.UNCLEAR,
            requests_goodbye=True,
        )
    if semantic.act == SemanticAct.GOODBYE_CONFIRM:
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.ANSWER,
            confirms_goodbye=True,
        )
    if semantic.act == SemanticAct.NO_ANSWER:
        return UserInterpretation(
            judgement=AnswerJudgement.NO_ANSWER,
            dialogue_act=DialogueAct.UNCLEAR,
        )
    return UserInterpretation(
        judgement=AnswerJudgement.UNCLEAR,
        dialogue_act=DialogueAct.UNCLEAR,
    )


def semantic_from_legacy(interp, *, text: str, answer_slot: str | None) -> SemanticTurn:
    """Bridge legacy UserInterpretation → SemanticTurn for migration."""
    from packages.contracts.enums import AnswerJudgement

    if getattr(interp, "confirms_goodbye", False):
        return SemanticTurn(
            act=SemanticAct.GOODBYE_CONFIRM,
            confidence=0.95,
            source_quote=text,
        )
    if getattr(interp, "requests_goodbye", False):
        return SemanticTurn(
            act=SemanticAct.GOODBYE_REQUEST,
            confidence=0.95,
            source_quote=text,
        )
    if getattr(interp, "requests_repeat", False):
        return SemanticTurn(
            act=SemanticAct.REPAIR_REQUEST,
            target_slot=answer_slot,
            repair=True,
            confidence=0.9,
            source_quote=text,
        )
    if interp.judgement == AnswerJudgement.BACKCHANNEL:
        return SemanticTurn(
            act=SemanticAct.BACKCHANNEL,
            target_slot=answer_slot,
            confidence=0.85,
            source_quote=text,
        )
    if interp.fact_candidates:
        cand = interp.fact_candidates[0]
        from packages.dialogue_engine.fast_interpreter import _detect_polarity

        pol = _detect_polarity(cand.value or text) or "positive"
        slot = cand.field
        return SemanticTurn(
            act=SemanticAct.ANSWER,
            answers_to=slot,
            target_slot=slot,
            slots={slot: SlotCandidate(value=cand.value, polarity=pol, confidence=0.9)},
            polarity=pol,
            confidence=0.9,
            source_quote=text,
            value=cand.value,
        )
    if interp.fills_pending_slot and answer_slot:
        return SemanticTurn(
            act=SemanticAct.ANSWER,
            target_slot=answer_slot,
            polarity="positive",
            confidence=0.85,
            source_quote=text,
            value=interp.slot_value or text,
        )
    if interp.judgement.name == "UNCLEAR":
        return SemanticTurn(
            act=SemanticAct.UNCLEAR,
            target_slot=answer_slot,
            confidence=0.7,
            source_quote=text,
        )
    return SemanticTurn(
        act=SemanticAct.UNCLEAR,
        target_slot=answer_slot,
        confidence=0.3,
        source_quote=text,
    )


def fast_interpret_legacy(text: str, *, answer_slot: str | None):
    """Compatibility shim for tests expecting (UserInterpretation, confident)."""
    from packages.dialogue_engine.context import InterpretContext
    from packages.dialogue_engine.contextual_interpreter import contextual_interpret
    from packages.dialogue_engine.state import EngineState

    state = EngineState(call_id="shim", elder_display_name="")
    if answer_slot:
        from packages.dialogue_engine.state import Question, QuestionPhase

        state.delivered_question = Question(
            question_id="q-shim",
            slot=answer_slot,
            text="",
            phase=QuestionPhase.DELIVERED,
        )
    ctx = InterpretContext.from_engine_state(state)
    sem, confident = contextual_interpret(text, ctx)
    return semantic_to_interpretation(sem), confident
