"""LLM message builder for CallMirror reply_stream."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from conversation_system.domain.turn_directive import TurnDirective
from conversation_system.reply.prompts import VERA_SYSTEM_PROMPT


def compose_turn_directive(
    *,
    observer_handling: str = "",
    goal_must_do: str = "",
    required_slot: str = "",
    required_action: str = "",
    current_slot: str = "",
    covered_slots: Sequence[str] = (),
    forbidden_slots: Sequence[str] = (),
    facts: Sequence[str] = (),
    pending_question: str = "",
    tone_policy: str = "",
) -> str:
    """Structured TurnDirective — observer + goal + agenda (merged, not OR)."""
    return TurnDirective.from_parts(
        observer_handling=observer_handling,
        goal_must_do=goal_must_do,
        required_slot=required_slot,
        required_action=required_action,
        current_slot=current_slot,
        covered_slots=covered_slots,
        forbidden_slots=forbidden_slots,
        facts=facts,
        pending_question=pending_question,
        tone_policy=tone_policy,
    ).format()


def build_llm_messages(
    mirror,
    plan: Dict[str, Any],
    *,
    max_history: int = 6,
) -> List[Dict[str, str]]:
    """OpenAI-style messages for one reply turn."""
    intent = (plan.get("intent") or "").strip()
    user_text = (plan.get("text") or "").strip()
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": VERA_SYSTEM_PROMPT},
    ]
    history = getattr(mirror, "llm_history", []) or []
    tail = history[-max_history:] if len(history) > max_history else history
    for role, content in tail:
        if role in ("user", "assistant") and (content or "").strip():
            messages.append({"role": role, "content": content.strip()})
    context_lines: List[str] = []
    if intent:
        context_lines.append(intent)
    facts = getattr(mirror, "facts", None) or []
    if facts:
        context_lines.append("Факты: " + "; ".join(str(f) for f in facts[-4:]))
    agenda_ctx = plan.get("agenda_context")
    if isinstance(agenda_ctx, Mapping):
        slot = str(agenda_ctx.get("current_slot") or "")
        covered = agenda_ctx.get("covered_slots") or ()
        forbidden = agenda_ctx.get("forbidden_slots") or ()
        if slot or covered or forbidden:
            directive = compose_turn_directive(
                current_slot=slot,
                covered_slots=tuple(covered),
                forbidden_slots=tuple(forbidden),
            )
            if directive:
                context_lines.append(directive)
    if context_lines:
        messages.append({
            "role": "assistant",
            "content": "\n".join(context_lines),
        })
    if user_text:
        messages.append({"role": "user", "content": user_text})
    return messages
