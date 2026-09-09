"""ResponsePlan — semantic action without fixed wording."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from packages.dialogue_engine.conversation_policy import ConversationObligation


class ResponseAction(StrEnum):
    ASK_ATTRIBUTE = "ask_attribute"
    ACKNOWLEDGE = "acknowledge"
    ANSWER_QUESTION = "answer_question"
    CLARIFY = "clarify"
    CONTROL = "control"
    CONTINUE_SLOT = "continue_slot"
    NEVER_SILENT = "never_silent"


class ResponsePlan(BaseModel):
    action: ResponseAction
    obligation: ConversationObligation
    episode_id: str | None = None
    attribute: str | None = None
    acknowledge: tuple[str, ...] = ()
    answer_user_question: str | None = None
    clarify_target: str | None = None
    safety_class: str | None = None
    allowed_facts: tuple[str, ...] = ()
    prohibited_inferences: tuple[str, ...] = Field(
        default_factory=lambda: ("diagnosis", "treatment", "prescription")
    )
    slot: str | None = None
    intent: str = ""
    marks_question: bool = False

    model_config = {"frozen": True}
