"""Strict phrase-renderer prompts — Qwen3-4B renders planner semantics only."""
from __future__ import annotations

import re
from typing import Any

from golden_path.content_plan import ContentPlan
from golden_path.spoken_surface import QUESTION_MEANING_RU

PHRASE_RENDERER_SYSTEM = (
    "Ты — Вера, голосовой помощник Имвера. "
    "Пишешь только реплику, которую скажешь по телефону. "
    "Женский род, обращение на «вы». "
    "Не объясняй задание. Не используй английские слова."
)

GREETING_TEXT = (
    "Здравствуйте! Это Вера из сервиса Имвера. "
    "Как у вас сегодня самочувствие?"
)

VERA_TONE_CONTRACT = PHRASE_RENDERER_SYSTEM

_CONTRAST_EXAMPLES = (
    "ПЛОХО: «Как прошлую ночь спал?» → ХОРОШО: «Как вы спали этой ночью?»\n"
    "ПЛОХО: «Попрощайтесь.» → ХОРОШО: «Берегите себя. До свидания.»\n"
    "ПЛОХО: «симптом knee» → ХОРОШО: «Поняла, речь о колене.»"
)


def build_renderer_prompt(
    content_plan: ContentPlan,
    user_message: str,
    *,
    correction_hint: str = "",
) -> str:
    """Assemble compact phrase-renderer user prompt."""
    lines = [
        "Ты Вера.",
        "Ответь пользователю по-русски.",
        "",
        f'Пользователь: "{user_message.strip()}"',
        "",
        "Смысл ответа:",
    ]
    for bullet in content_plan.semantic_bullets:
        lines.append(f"- {bullet}")
    if content_plan.required_meaning_ru:
        lines.append(f"- {content_plan.required_meaning_ru}")
    if content_plan.example_realization:
        lines.append(f"Пример смысла (не копируй дословно): «{content_plan.example_realization}»")
    if content_plan.facts_to_reference:
        lines.append("")
        lines.append("Контекст:")
        for fact in content_plan.facts_to_reference:
            lines.append(f"- {fact}")
    if content_plan.required_question:
        meaning = QUESTION_MEANING_RU.get(
            content_plan.required_question, content_plan.required_question
        )
        lines.append(f"Вопрос должен быть про: {meaning}")
    if content_plan.forbidden_topics:
        lines.append(f"Не спрашивать: {', '.join(content_plan.forbidden_topics)}.")
    if content_plan.do_not_say:
        lines.append(f"Нельзя: {'; '.join(content_plan.do_not_say[:4])}.")
    lines.extend(
        [
            "",
            "Одна-две короткие фразы. Максимум один вопрос.",
            "Не используй английские слова. Не объясняй задание.",
            "Выведи только реплику Веры.",
            "",
            _CONTRAST_EXAMPLES,
        ]
    )
    if correction_hint:
        lines.extend(["", f"Исправление: {correction_hint.strip()}"])
    return "\n".join(lines)


def build_user_prompt(
    action: str,
    user_message: str,
    state_compact: dict[str, Any],
    already_answered: list[Any],
    do_not_ask: list[Any],
    slot: Any = None,
    last_assistant: str = "",
    answer_type: Any = None,
    content_plan: ContentPlan | None = None,
) -> str:
    """Backward-compatible entry — prefers content_plan when provided."""
    if content_plan is not None:
        return build_renderer_prompt(content_plan, user_message)
    return (
        f"ACTION: {action}\n"
        f"USER SAID: {user_message.strip()}\n"
        f"STATE: {state_compact}\n"
        "OUTPUT: 1–2 короткие русские фразы."
    )


_THINK_TAG = "redacted_thinking"
_THINKING_BLOCK_RE = re.compile(
    rf"<{_THINK_TAG}>.*?</{_THINK_TAG}>",
    re.DOTALL | re.IGNORECASE,
)


def clean_llm_output(text: str) -> str:
    if not text:
        return ""
    out = text.strip()
    out = _THINKING_BLOCK_RE.sub("", out)
    out = re.sub(r"</?think>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"^[\"'«]+|[\"'»]+$", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"^ACTION:\s*\S+\s*", "", out, flags=re.IGNORECASE)
    return out.strip()


def contains_thinking_leak(text: str) -> bool:
    low = (text or "").lower()
    if "reasoning_content" in low:
        return True
    if _THINK_TAG in low:
        return True
    if "<think" in low:
        return True
    return False
