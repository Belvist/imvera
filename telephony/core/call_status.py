"""Family-facing call statuses (ROADMAP E2).

Agent safety outcomes (ok / attention / alert / unknown) map to a fixed
family vocabulary. Technical failures MUST become TECHNICAL and never GREEN.
"""

from enum import Enum


SCENARIO_VERSION = "scenario-v1"
SAFETY_RULES_VERSION = "safety-v1"

_AGENT_TO_FAMILY = {
    "ok": "green",
    "attention": "yellow",
    "alert": "red",
    "unknown": "technical",
    "no_speech": "no_contact",
    "no_contact": "no_contact",
    "declined": "declined",
    "technical": "technical",
}


class CallStatus(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    NO_CONTACT = "no_contact"
    TECHNICAL = "technical"
    DECLINED = "declined"


def from_agent_outcome(status: str) -> CallStatus:
    """Map Agent.outcome status / legacy verdict → family CallStatus."""
    key = (status or "").strip().lower()
    mapped = _AGENT_TO_FAMILY.get(key)
    if mapped is None:
        return CallStatus.TECHNICAL
    return CallStatus(mapped)


def resolve_family_status(agent_status, *, technical_error=None,
                          no_contact=False, declined=False,
                          wellness_band=None) -> CallStatus:
    """Final family status with hard overrides.

    TECHNICAL always wins over a green-looking agent status when a hard
    STT/LLM/TTS failure was recorded. Alert stays RED (never TECHNICAL).
    """
    if technical_error:
        return CallStatus.TECHNICAL
    if declined or (agent_status or "").strip().lower() == "declined":
        return CallStatus.DECLINED
    if no_contact or (agent_status or "").strip().lower() in (
            "no_contact", "no_speech"):
        return CallStatus.NO_CONTACT
    status = from_agent_outcome(agent_status)
    band = (wellness_band or "").strip().lower()
    if band in ("bad", "medium") and status is CallStatus.GREEN:
        return CallStatus.YELLOW
    if band == "critical" and status in (CallStatus.GREEN, CallStatus.YELLOW):
        return CallStatus.RED
    return status


def build_reasons(notes=None, facts=None, status=None,
                  technical_error=None) -> list:
    """Compact reason tags for storage (not a transcript dump)."""
    reasons = []
    if status is not None:
        value = status.value if isinstance(status, CallStatus) else str(status)
        reasons.append(f"status:{value}")
    if technical_error:
        reasons.append(f"technical:{str(technical_error)[:200]}")
    for note in notes or []:
        text = str(note or "").strip()
        if text:
            reasons.append(f"note:{text[:160]}")
    for fact in facts or []:
        text = str(fact or "").strip()
        if text:
            reasons.append(f"fact:{text[:120]}")
    return reasons


_STATUS_LEAD = {
    CallStatus.GREEN: (
        "Звонок прошёл спокойно. Самочувствие в порядке."),
    CallStatus.YELLOW: (
        "В разговоре появились моменты, на которые стоит обратить внимание."),
    CallStatus.RED: (
        "Во время звонка зафиксирована тревожная ситуация. "
        "Нужна проверка близкими."),
    CallStatus.NO_CONTACT: (
        "Дозвониться или услышать ответ не удалось. "
        "Связь с абонентом не состоялась."),
    CallStatus.TECHNICAL: (
        "Звонок завершился из‑за технической ошибки. "
        "Это не оценка самочувствия."),
    CallStatus.DECLINED: (
        "Абонент отказался от разговора или не дал согласие. "
        "Звонок завершён без проверки самочувствия."),
}


def summary_for_family(notes=None, facts=None, status=None) -> str:
    """Deterministic Russian 2–3 sentence summary for the family app.

    Never dumps raw transcripts — only curated notes/facts and the status.
    """
    if isinstance(status, CallStatus):
        cs = status
    else:
        cs = from_agent_outcome(status) if status else CallStatus.TECHNICAL

    parts = [_STATUS_LEAD[cs]]

    clean_notes = [str(n).strip() for n in (notes or []) if str(n).strip()]
    clean_facts = [str(f).strip() for f in (facts or []) if str(f).strip()]

    if cs is CallStatus.TECHNICAL:
        tech = next((n for n in clean_notes if n.startswith("ошибка:")), None)
        if tech:
            parts.append(f"Причина: {tech[7:].strip() or 'сбой сервиса'}.")
        else:
            parts.append("Повторите попытку позже или проверьте сервис.")
        return " ".join(parts)

    if cs is CallStatus.DECLINED:
        parts.append("Повторный звонок возможен только после нового согласия.")
        return " ".join(parts)

    if cs is CallStatus.NO_CONTACT:
        parts.append("Близким стоит попробовать связаться самостоятельно.")
        return " ".join(parts)

    # GREEN / YELLOW / RED — weave a short note/fact sentence when present.
    highlight = clean_notes[:2] or clean_facts[:2]
    if highlight:
        joined = "; ".join(highlight[:2])
        if len(joined) > 180:
            joined = joined[:177] + "…"
        parts.append(f"Отмечено: {joined}.")
    elif cs is CallStatus.GREEN:
        parts.append("Дополнительных замечаний нет.")
    elif cs is CallStatus.YELLOW:
        parts.append("Рекомендуем уточнить самочувствие при удобном случае.")
    else:  # RED
        parts.append("Сообщение семье уже поставлено в очередь уведомлений.")

    if clean_facts and clean_notes:
        # Third sentence only when both streams have content.
        fact_bit = clean_facts[0]
        if len(fact_bit) > 100:
            fact_bit = fact_bit[:97] + "…"
        parts.append(f"Из разговора: {fact_bit}.")

    return " ".join(parts[:3])


def family_fields_for_finalize(agent_status, notes=None, facts=None,
                               technical_error=None, no_contact=False,
                               declined=False, wellness_band=None) -> dict:
    """Bundle columns written into call_results on finalize."""
    status = resolve_family_status(
        agent_status,
        technical_error=technical_error,
        no_contact=no_contact,
        declined=declined,
        wellness_band=wellness_band,
    )
    # Hard invariant: technical failure can never stay GREEN.
    if technical_error and status is CallStatus.GREEN:
        status = CallStatus.TECHNICAL
    notes_list = list(notes or [])
    if technical_error:
        tag = f"ошибка: {technical_error}"
        if tag not in notes_list:
            notes_list = notes_list + [tag]
    reasons = build_reasons(
        notes=notes_list, facts=facts, status=status,
        technical_error=technical_error)
    return {
        "family_status": status.value,
        "reasons": reasons,
        "summary_for_family": summary_for_family(
            notes=notes_list, facts=facts, status=status),
        "scenario_version": SCENARIO_VERSION,
        "safety_rules_version": SAFETY_RULES_VERSION,
        "technical_error": (
            str(technical_error)[:500] if technical_error else None),
    }
