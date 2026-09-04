"""ConversationFacade — production-ready API for orchestrator cutover."""
from __future__ import annotations

import threading
from typing import Iterator, Mapping, Sequence

from conversation_system.domain.api import (
    CallSummary,
    SessionHandle,
    SessionNotFound,
    TurnCommit,
    TurnPlanV2,
)
from conversation_system.domain.understanding import FamilyQuestion
from conversation_system.runtime.session import ConversationSession, TurnPipeline


class ConversationFacade:
    """Thread-safe registry of per-call ConversationSession instances."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        self._lock = threading.RLock()
        self._pipeline = TurnPipeline()

    def begin_call(
        self,
        *,
        call_id: str,
        caller_id: str = "",
        elder_context: Mapping[str, str] | None = None,
        mode: str = "check_in",
        family_questions: Sequence[Mapping[str, str]] | None = None,
        greeting_played: bool = False,
    ) -> tuple[SessionHandle, str]:
        session = ConversationSession(call_id=call_id)
        if family_questions:
            session.agenda.inject_family_questions(family_questions)
            session.memory.family_questions = [
                FamilyQuestion(
                    id=str(q.get("id") or ""),
                    text=str(q.get("text") or ""),
                    author=str(q.get("author") or "Родные"),
                )
                for q in family_questions
                if q.get("text")
            ]
        greeting = self._pipeline.begin(
            session,
            caller_id=caller_id,
            greeting_played=greeting_played,
        )
        handle = SessionHandle(call_id=call_id, internal_id=session.internal_id)
        with self._lock:
            self._sessions[session.internal_id] = session
        return handle, greeting

    def plan_turn(
        self,
        handle: SessionHandle,
        *,
        transcript: str = "",
        reason: str | None = None,
        stt_confidence: float | None = None,
    ) -> TurnPlanV2:
        session = self._get_session(handle)
        return self._pipeline.plan_turn(
            session,
            transcript=transcript,
            reason=reason,
            stt_confidence=stt_confidence,
        )

    def stream_reply(
        self,
        handle: SessionHandle,
        plan: TurnPlanV2,
    ) -> Iterator[str]:
        session = self._get_session(handle)
        return self._pipeline.stream_reply(session, plan)

    def commit_turn(
        self,
        handle: SessionHandle,
        plan: TurnPlanV2,
        spoken_text: str,
    ) -> TurnCommit:
        session = self._get_session(handle)
        return self._pipeline.commit_turn(session, plan, spoken_text)

    def mark_segment_played(
        self,
        handle: SessionHandle,
        *,
        generation_id: int,
        segment_id: str = "",
        slot: str = "",
    ) -> None:
        session = self._get_session(handle)
        self._pipeline.mark_segment_played(
            session,
            generation_id=generation_id,
            segment_id=segment_id,
            slot=slot,
        )

    def on_generation_cancelled(
        self,
        handle: SessionHandle,
        *,
        generation_id: int,
    ) -> None:
        session = self._get_session(handle)
        self._pipeline.on_generation_cancelled(
            session,
            generation_id=generation_id,
        )

    def end_call(self, handle: SessionHandle) -> CallSummary:
        session = self._get_session(handle)
        summary = self._pipeline.end_call(session)
        with self._lock:
            self._sessions.pop(session.internal_id, None)
        return summary

    def _get_session(self, handle: SessionHandle) -> ConversationSession:
        with self._lock:
            session = self._sessions.get(handle.internal_id)
        if session is None or session.call_id != handle.call_id:
            raise SessionNotFound(f"unknown session {handle.call_id}")
        return session


_facade_singleton: ConversationFacade | None = None
_facade_lock = threading.Lock()


def get_conversation_facade() -> ConversationFacade:
    """Process-wide facade instance (orchestrator wiring phase 4)."""
    global _facade_singleton
    with _facade_lock:
        if _facade_singleton is None:
            _facade_singleton = ConversationFacade()
        return _facade_singleton
