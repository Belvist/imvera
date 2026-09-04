"""Per-call dialogue mirror — echo-guard and session emit fields only.

Orchestrator keeps a lightweight mirror; ConversationFacade owns dialogue logic.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Iterator, List, Mapping, Sequence, Tuple

from conversation_system.reply.llm_context import build_llm_messages

_LOG = logging.getLogger(__name__)


def _llm_timeout_s() -> float:
    """Seconds CallMirror waits for streamed LLM output before pool fallback."""
    raw = os.environ.get("MOSS_LLM_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(0.5, float(raw))
        except ValueError:
            _LOG.warning("call_mirror invalid MOSS_LLM_TIMEOUT_S=%r; using 8.0", raw)
    return 8.0


_LLM_TIMEOUT_S = _llm_timeout_s()


class CallMirror:
    """Mutable per-call state mirrored from ConversationFacade commits."""

    def __init__(self, llm=None) -> None:
        self.llm = llm
        self._last_reply = ""
        self._call_greeting = ""
        self.llm_history: List[Tuple[str, str]] = []
        self.notes: List[str] = []
        self.status = "ok"
        self.done = False
        self.step = 0
        self.last_intent = ""
        self.technical_error: str | None = None
        self._consent_declined = False
        self._consent_granted = False
        self._consent_method: str | None = None
        self._consent_call = False
        self._consent_empty = 0
        self._last_confidence: float | None = None
        self.facts: List[str] = []
        self.family_questions: List[Dict[str, Any]] = []
        self._elder_display_name: str | None = None
        self._elder_timezone: str | None = None
        self._pg = None
        self._person_id: str | None = None
        self._household_id: str | None = None

    @property
    def finished(self) -> bool:
        return self.done

    @finished.setter
    def finished(self, value: bool) -> None:
        self.done = bool(value)

    @property
    def outcome(self) -> Dict[str, Any]:
        return {"status": self.status, "notes": list(self.notes)}

    def set_elder_context(
        self,
        *,
        display_name: str | None = None,
        timezone: str | None = None,
    ) -> None:
        if display_name:
            self._elder_display_name = str(display_name)
        if timezone:
            self._elder_timezone = str(timezone)

    def set_family_questions(
        self,
        questions: Sequence[Mapping[str, Any]] | None,
    ) -> None:
        self.family_questions = [
            dict(q) for q in (questions or []) if q.get("text")
        ]

    def observe_confidence(self, confidence: float | None) -> None:
        if confidence is not None:
            self._last_confidence = confidence

    def mark_technical(self, reason: str) -> None:
        reason = str(reason or "unknown").strip() or "unknown"
        self.technical_error = reason
        if self.status in ("ok", "unknown", ""):
            self.status = "technical"
        note = f"ошибка: {reason}"
        if note not in self.notes:
            self.notes.append(note)

    def _note(self, text: str) -> None:
        t = (text or "").strip()
        if t and t not in self.notes:
            self.notes.append(t)

    def record_user(self, text: str) -> None:
        t = (text or "").strip()
        if t:
            self.llm_history.append(("user", t))

    def commit_reply(self, spoken: str) -> None:
        reply = (spoken or "").strip()
        if reply:
            self._last_reply = reply
            self.llm_history.append(("assistant", reply))

    def reply_stream(self, plan: Dict[str, Any]) -> Iterator[str]:
        """Stream LLM deltas when allowed; otherwise yield pool fallback."""
        fb = (plan or {}).get("fallback") or ""
        if not plan or not plan.get("allow_llm") or self.llm is None:
            if fb:
                yield fb
            return
        if not (plan.get("text") or "").strip():
            if fb:
                yield fb
            return
        messages = build_llm_messages(self, plan)
        got = False
        llm_error: str | None = None
        try:
            stream = self.llm.chat_stream(
                messages, max_tokens=100, temp=0.65, timeout=_LLM_TIMEOUT_S)
            for delta in stream:
                if delta:
                    got = True
                    yield delta
        except Exception as exc:  # noqa: BLE001
            llm_error = str(exc)
            _LOG.warning("call_mirror llm_stream failed: %s", exc)
            got = False
        if not got and fb:
            if llm_error:
                _LOG.warning(
                    "call_mirror llm_stream error (timeout=%.1fs): %s → pool fallback",
                    _LLM_TIMEOUT_S,
                    llm_error,
                )
            else:
                _LOG.warning(
                    "call_mirror llm_stream empty (timeout=%.1fs) → pool fallback",
                    _LLM_TIMEOUT_S,
                )
            yield fb
