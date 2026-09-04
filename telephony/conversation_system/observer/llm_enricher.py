"""Optional LLM enrichment for Observer — structured JSON, fail-closed."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from conversation_system.domain.understanding import TurnUnderstanding
    from conversation_system.memory.state import ConversationMemory

_LOG = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 2.5
_MAX_FACTS = 5
_MAX_LIST_ITEMS = 3
_MAX_DIRECTIVE_LEN = 300

_OBSERVER_SYSTEM = (
    "Ты Observer для голосового ассистента Вера (забота о пожилых). "
    "По реплике абонента верни ТОЛЬКО JSON без markdown:\n"
    '{"facts":["..."],"corrections":["..."],"contradictions":["..."],'
    '"next_directive_hint":"..."}\n'
    "facts — новые факты о самочувствии (≤5 коротких строк). "
    "corrections — если абонент исправляет прошлое (≤3). "
    "contradictions — противоречия с прошлым (≤3). "
    "next_directive_hint — одна подсказка для ответа (≤200 символов, "
    "без обещаний вызвать врача/скорую/родных). "
    "Пустые массивы и пустая строка — если нечего добавить."
)


@dataclass(frozen=True)
class LlmEnrichment:
    """Validated partial observer output from LLM."""

    facts: tuple[str, ...] = ()
    corrections: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    next_directive_hint: str = ""


def observer_llm_enabled() -> bool:
    """Env gate — default on when an LLM client is wired."""
    raw = os.environ.get("MOSS_OBSERVER_LLM", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def observer_llm_blocking_enabled() -> bool:
    """When false (default), LLM enricher does not block the turn hot path."""
    raw = os.environ.get("MOSS_OBSERVER_LLM_BLOCKING", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


class LlmObserverEnricher:
    """Calls LLM with bounded timeout; returns None on any failure."""

    def __init__(
        self,
        llm: Any = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._llm = llm
        self._timeout = timeout

    def set_llm(self, llm: Any) -> None:
        self._llm = llm

    @property
    def llm(self) -> Any:
        return self._llm

    def enrich(
        self,
        memory: "ConversationMemory",
        understanding: "TurnUnderstanding",
        *,
        base_directive: str = "",
    ) -> LlmEnrichment | None:
        if self._llm is None or not observer_llm_enabled():
            return None
        chat_fn = getattr(self._llm, "chat", None)
        if not callable(chat_fn):
            return None
        user_text = (understanding.clean_text or "").strip()
        if not user_text:
            return None
        messages = self._build_messages(memory, user_text, base_directive)
        try:
            raw = chat_fn(
                messages,
                max_tokens=180,
                temp=0.35,
                timeout=self._timeout,
            )
        except Exception as exc:
            _LOG.warning(
                "observer_llm_call_failed call_id=%s err=%s",
                memory.call_id,
                exc,
            )
            return None
        if not raw or not str(raw).strip():
            return None
        parsed = _parse_observer_json(str(raw))
        if parsed is None:
            _LOG.warning(
                "observer_llm_invalid_json call_id=%s",
                memory.call_id,
            )
            return None
        return parsed

    def _build_messages(
        self,
        memory: "ConversationMemory",
        user_text: str,
        base_directive: str,
    ) -> list[dict[str, str]]:
        context_lines = memory.to_skill_context_lines()
        ctx = "\n".join(context_lines) if context_lines else "(нет контекста)"
        user_block = (
            f"Контекст:\n{ctx}\n\n"
            f"Последний вопрос Веры: {memory.last_question or '—'}\n"
            f"Базовая подсказка: {base_directive or '—'}\n\n"
            f"Реплика абонента: «{user_text[:400]}»"
        )
        return [
            {"role": "system", "content": _OBSERVER_SYSTEM},
            {"role": "user", "content": user_block},
        ]


def _parse_observer_json(raw: str) -> LlmEnrichment | None:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    facts = _clean_str_list(data.get("facts"), _MAX_FACTS)
    corrections = _clean_str_list(data.get("corrections"), _MAX_LIST_ITEMS)
    contradictions = _clean_str_list(data.get("contradictions"), _MAX_LIST_ITEMS)
    hint = _clean_directive(data.get("next_directive_hint"))
    return LlmEnrichment(
        facts=facts,
        corrections=corrections,
        contradictions=contradictions,
        next_directive_hint=hint,
    )


def _clean_str_list(value: Any, limit: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    for item in value[:limit]:
        if not isinstance(item, str):
            continue
        s = " ".join(item.split()).strip()
        if s and s not in out:
            out.append(s[:200])
    return tuple(out)


def _clean_directive(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    s = " ".join(value.split()).strip()
    if not s:
        return ""
    return s[:_MAX_DIRECTIVE_LEN]
