"""Prompt-contract v1 for the conversation model (Cut-0/1 groundwork).

Lessons from bench_conversation_models (measured, not opined):
- alternating user/assistant messages beat one blob;
- raw goal-ids leak into speech (4B: «лекарства и визит дочери — всё на месте»);
- small models parrot the greeting and garble tone without explicit bans.

Contract: natural-language objectives only, hard bans, 1-2 phrases.
"""

from __future__ import annotations

SYSTEM_V1 = (
    "Ты Вера, заботливая собеседница сервиса заботы о пожилых. "
    "Ты разговариваешь с пожилым человеком по телефону. "
    "Отвечай КАК Вера — одной-двумя короткими фразами, не анализируй разговор. "
    "Продолжай мысль человека, если он что-то рассказал. "
    "Обращайся на «вы». "
    "Запрещено: задавать больше одного вопроса; обещать действия "
    "(вызвать, приехать, гарантировать); повторять приветствие; "
    "называть время суток; перечислять служебные цели; говорить о себе как о программе."
)


def build_messages(
    history: list[tuple[str, str]],
    user_text: str,
    known: str,
    objectives: str,
    banned: str = "",
) -> list[dict[str, str]]:
    """history: [(role, text)] with role in user/assistant, oldest first."""
    state_block = (
        "СЛУЖЕБНО, не повторять вслух. "
        f"Точно известно: {known}. Желательно узнать: {objectives}."
    )
    if banned:
        state_block += f" Не спрашивать снова: {banned}."
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_V1}]
    for role, text in history[-8:]:
        messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": f"{state_block}\n\nЧеловек: {user_text}"})
    return messages
