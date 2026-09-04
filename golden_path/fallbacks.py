"""Typed deterministic fallbacks per planner action — no universal ACK."""
from __future__ import annotations

from golden_path.analyzer import AnswerType
from golden_path.planner import PlannerAction
from golden_path.slots import SlotName
from golden_path.spoken_surface import symptom_prep_phrase
from golden_path.state import ConversationState

SAFETY_FALLBACK = (
    "Понимаю, это важно. Оставайтесь на линии, если вам плохо."
)

ASK_SLOT_FALLBACKS: dict[SlotName, str] = {
    SlotName.WELLNESS: "Как вы сейчас себя чувствуете?",
    SlotName.MOOD: "Какое у вас сегодня настроение?",
    SlotName.SLEEP: "Как вы спали этой ночью?",
    SlotName.PLANS: "Что планируете на сегодня?",
}

ANSWER_TYPE_FALLBACKS: dict[AnswerType, str] = {
    AnswerType.IDENTITY: (
        "Я Вера, голосовой помощник сервиса Имвера. "
        "Звоню, чтобы узнать, как вы себя чувствуете."
    ),
    AnswerType.WHY_CALLING: (
        "Мы звоним, чтобы узнать, как вы себя чувствуете."
    ),
    AnswerType.PRIVACY: (
        "Ваши ответы видят только близкие, которых вы подключили к сервису. "
        "Я не спрашиваю паспорт, адрес и другие личные данные."
    ),
    AnswerType.OTHER: (
        "Я не могу ответить на это точно, но я здесь, чтобы узнать, "
        "как вы себя чувствуете."
    ),
}

ACTION_FALLBACKS: dict[PlannerAction, str] = {
    PlannerAction.GREET: (
        "Здравствуйте! Это Вера из Имвера. Как у вас самочувствие?"
    ),
    PlannerAction.WAIT: "Конечно, я подожду.",
    PlannerAction.HANDLE_FATIGUE: "Понимаю. Можем на этом закончить.",
    PlannerAction.HANDLE_REFUSAL: "Хорошо, не будем об этом.",
    PlannerAction.HANDLE_CORRECTION: "Поняла, спасибо за уточнение.",
    PlannerAction.SAFETY: SAFETY_FALLBACK,
    PlannerAction.CLOSE: "Хорошо. Берегите себя, до свидания.",
    PlannerAction.ACK_ONLY: "Понимаю.",
}


def repair_fallback(state: ConversationState) -> str:
    """Repeat the actual last assistant question — not a generic substitute."""
    last_q = (state.pending_question or state.last_assistant_text or "").strip()
    if last_q:
        return last_q
    return "Как вы сегодня себя чувствуете?"


def correction_fallback(state: ConversationState) -> str:
    symptom = str(state.facts.get("symptom") or "")
    prep = symptom_prep_phrase(symptom)
    if prep:
        return f"Поняла, спасибо за уточнение — речь о {prep}."
    return ACTION_FALLBACKS[PlannerAction.HANDLE_CORRECTION]


def typed_fallback(
    action: PlannerAction,
    state: ConversationState,
    slot: SlotName | None = None,
    answer_type: AnswerType | None = None,
) -> str:
    if action == PlannerAction.ASK_SLOT and slot is not None:
        return ASK_SLOT_FALLBACKS[slot]
    if action == PlannerAction.ANSWER_USER:
        if answer_type is not None:
            return ANSWER_TYPE_FALLBACKS.get(
                answer_type, ANSWER_TYPE_FALLBACKS[AnswerType.OTHER]
            )
        return ANSWER_TYPE_FALLBACKS[AnswerType.OTHER]
    if action == PlannerAction.REPAIR:
        return repair_fallback(state)
    if action == PlannerAction.HANDLE_CORRECTION:
        return correction_fallback(state)
    return ACTION_FALLBACKS.get(action, "Понимаю.")
