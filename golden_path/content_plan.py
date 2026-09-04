"""Semantic content plan — planner intent for phrase renderer (not LLM-invented)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from golden_path.analyzer import Analysis, AnswerType
from golden_path.planner import Plan, PlannerAction
from golden_path.slots import SlotName, SLOT_LABELS_RU, SLOT_ORDER, SlotStatus
from golden_path.spoken_surface import (
    FORBIDDEN_TOPIC_RU,
    QUESTION_MEANING_RU,
    SLOT_QUESTION_EXAMPLE,
    format_facts_ru,
    symptom_prep_phrase,
)
from golden_path.state import ConversationState

_SLOT_QUESTION_KEY: dict[SlotName, str] = {
    SlotName.WELLNESS: "wellness_now",
    SlotName.MOOD: "mood_today",
    SlotName.SLEEP: "sleep_last_night",
    SlotName.PLANS: "plans_today",
}


@dataclass(frozen=True)
class ContentPlan:
    """What the phrase renderer must express — planner-owned semantics."""

    action: str
    response_intent: str
    facts_to_reference: tuple[str, ...]
    required_question: str | None
    forbidden_topics: tuple[str, ...]
    semantic_bullets: tuple[str, ...]
    required_meaning_ru: str | None = None
    example_realization: str | None = None
    do_not_say: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "response_intent": self.response_intent,
            "facts_to_reference": list(self.facts_to_reference),
            "required_question": self.required_question,
            "forbidden_topics": list(self.forbidden_topics),
            "semantic_bullets": list(self.semantic_bullets),
            "required_meaning_ru": self.required_meaning_ru,
            "example_realization": self.example_realization,
            "do_not_say": list(self.do_not_say),
        }


def _blocked_slot_labels(state: ConversationState) -> tuple[str, ...]:
    blocked: list[str] = []
    for slot in SLOT_ORDER:
        status = state.slot_statuses.get(slot, SlotStatus.OPEN)
        if status in (SlotStatus.ANSWERED, SlotStatus.DECLINED):
            blocked.append(slot.value)
    return tuple(blocked)


def _user_polarity_hint(text: str) -> str | None:
    low = (text or "").lower()
    if any(w in low for w in ("плохо", "устал", "болит", "трудно", "не очень")):
        return "negative_or_mixed"
    if any(w in low for w in ("хорошо", "нормально", "отлично", "спокойн", "неплохо")):
        return "positive_or_neutral"
    return None


def build_content_plan(
    plan: Plan,
    state: ConversationState,
    analysis: Analysis,
    user_message: str,
) -> ContentPlan:
    """Derive renderer semantics from planner action + reduced state."""
    action_name = plan.action_name()
    blocked = _blocked_slot_labels(state)
    polarity = _user_polarity_hint(user_message)
    facts_ru = format_facts_ru({k: str(v) for k, v in state.facts.items() if v})
    bullets: list[str] = []
    intent = "neutral_ack"
    required_q: str | None = None
    required_meaning: str | None = None
    example: str | None = None
    do_not: list[str] = [
        "инструкции пользователю (попрощайтесь, спросите и т.п.)",
        "английские слова",
        "внутренние метки (knee, sleep_last_night)",
        "мужской род от лица Веры",
        "угадывание пола пользователя",
        "«вы выглядите» / «я вижу»",
    ]
    forbidden = [FORBIDDEN_TOPIC_RU.get(t, t) for t in blocked]

    if plan.action == PlannerAction.ASK_SLOT and plan.slot is not None:
        label = SLOT_LABELS_RU[plan.slot]
        q_key = _SLOT_QUESTION_KEY[plan.slot]
        required_q = q_key
        required_meaning = QUESTION_MEANING_RU[q_key]
        example = SLOT_QUESTION_EXAMPLE[plan.slot]
        intent = "ask_slot_with_brief_ack"
        if polarity == "positive_or_neutral":
            bullets.append("коротко позитивно отреагировать на сказанное")
        elif polarity == "negative_or_mixed":
            bullets.append("коротко сочувственно отреагировать на сказанное")
        else:
            bullets.append("коротко откликнуться на сказанное")
        bullets.append(f"задать один вопрос про {label}")
        bullets.append("формулировка без угадывания пола (используйте «вы спали», не «спал»)")
        for slot in SLOT_ORDER:
            if slot != plan.slot:
                forbidden.append(SLOT_LABELS_RU[slot])

    elif plan.action == PlannerAction.ACK_ONLY:
        intent = "narrative_ack"
        required_meaning = "коротко откликнуться на рассказ без нового вопроса"
        example = "Понимаю."
        bullets.append(required_meaning)
        forbidden.extend(SLOT_LABELS_RU[s] for s in SLOT_ORDER)

    elif plan.action == PlannerAction.WAIT:
        intent = "wait_ack"
        required_meaning = "подтвердить, что подождёте"
        example = "Конечно, я подожду."
        bullets.append(required_meaning)
        bullets.append("без нового вопроса")

    elif plan.action == PlannerAction.HANDLE_FATIGUE:
        intent = "fatigue_respect"
        required_meaning = "признать усталость пользователя и предложить закончить"
        example = "Понимаю. Можем на этом закончить."
        bullets.append("пользователь устал отвечать — не говорите, что устали вы")
        bullets.append("без нового вопроса по повестке")

    elif plan.action == PlannerAction.HANDLE_REFUSAL:
        intent = "accept_refusal"
        required_meaning = "принять отказ без давления"
        example = "Хорошо, не будем об этом."
        slot = plan.slot
        if slot is not None:
            bullets.append(f"пользователь отказался от темы «{SLOT_LABELS_RU[slot]}»")
        bullets.append("без нового вопроса")

    elif plan.action == PlannerAction.HANDLE_CORRECTION:
        intent = "acknowledge_correction"
        symptom = state.facts.get("symptom") or analysis.facts.get("symptom")
        prep = symptom_prep_phrase(str(symptom)) if symptom else None
        if prep:
            required_meaning = f"подтвердить, что речь о {prep}"
            example = f"Поняла, спасибо за уточнение — речь о {prep}."
            bullets.append(required_meaning)
        else:
            bullets.append("признать исправление пользователя")
            example = "Поняла, спасибо за уточнение."
        bullets.append("без вопроса")

    elif plan.action == PlannerAction.REPAIR:
        intent = "repeat_last_question"
        last_q = state.pending_question or state.last_assistant_text
        if last_q:
            bullets.append(f"повторить предыдущий вопрос: «{last_q[:100]}»")
            required_meaning = "повторить тот же вопрос, не задавать новый"
            example = last_q[:120]
        else:
            bullets.append("повторить последний вопрос о самочувствии")

    elif plan.action == PlannerAction.ANSWER_USER:
        at = plan.answer_type or AnswerType.OTHER
        intent = f"answer_user_{at.value.lower()}"
        if at == AnswerType.IDENTITY:
            required_meaning = "представиться как Вера из Имвера"
        elif at == AnswerType.WHY_CALLING:
            required_meaning = "объяснить цель звонка — узнать самочувствие"
        elif at == AnswerType.PRIVACY:
            required_meaning = "объяснить, кто видит ответы"
        else:
            required_meaning = "честно ответить без выдумок"
        bullets.append(required_meaning)
        bullets.append("без вопроса по повестке в этом же ответе")
        forbidden.extend(SLOT_LABELS_RU[s] for s in SLOT_ORDER)

    elif plan.action == PlannerAction.CLOSE:
        intent = "warm_close"
        required_meaning = "тепло попрощаться от лица Веры"
        example = "Хорошо. Берегите себя, до свидания."
        bullets.append(required_meaning)
        bullets.append("не давать инструкций пользователю")
        bullets.append("без новых вопросов")

    elif plan.action == PlannerAction.SAFETY:
        intent = "safety_empathy"
        required_meaning = (
            "выразить заботу; попросить оставаться на линии, если плохо"
        )
        bullets.append(required_meaning)
        do_not.append("обещать записать или передать близким без подтверждённого действия")

    elif plan.action == PlannerAction.GREET:
        intent = "greet_wellness"
        required_q = _SLOT_QUESTION_KEY[SlotName.WELLNESS]
        required_meaning = QUESTION_MEANING_RU[required_q]
        example = SLOT_QUESTION_EXAMPLE[SlotName.WELLNESS]
        bullets.append("поприветствовать и спросить про самочувствие")

    return ContentPlan(
        action=action_name,
        response_intent=intent,
        facts_to_reference=tuple(facts_ru),
        required_question=required_q,
        forbidden_topics=tuple(sorted(set(forbidden))),
        semantic_bullets=tuple(bullets),
        required_meaning_ru=required_meaning,
        example_realization=example,
        do_not_say=tuple(do_not),
    )


def build_correction_hint(
    violations: list[str],
    plan: Plan,
    content_plan: ContentPlan,
) -> str:
    """One-line correction for single regenerate pass."""
    parts = ["Исправь ответ."]
    if plan.action == PlannerAction.ASK_SLOT and plan.slot is not None:
        label = SLOT_LABELS_RU[plan.slot]
        parts.append(f"Требуется только вопрос про {label}.")
        parts.append("Без угадывания пола: «вы спали», не «спал».")
    if "too_many_questions" in violations or any("reask_" in v for v in violations):
        parts.append("Максимум один вопрос.")
    if any("reask_" in v for v in violations):
        parts.append("Не спрашивай уже закрытые темы.")
    if "question_on_answer_user" in violations:
        parts.append("Ответь на вопрос без своего вопроса.")
    if any(v.startswith("spoken:") for v in violations):
        parts.append("Только естественный русский от лица Веры. Без английских слов.")
    if "question_on_wait" in violations or "question_on_ack_only" in violations:
        parts.append("Без вопросительного знака.")
    if content_plan.forbidden_topics:
        parts.append(
            "Не спрашивай: " + ", ".join(content_plan.forbidden_topics[:6]) + "."
        )
    parts.append("Одна-две короткие фразы.")
    return " ".join(parts)
