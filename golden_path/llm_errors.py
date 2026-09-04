"""Typed LLM runtime failures — never masked by dialogue fallbacks."""
from __future__ import annotations


class LLMRuntimeError(Exception):
    """Raised when local LLM cannot produce a dialogue reply."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        message = code if not detail else f"{code}: {detail}"
        super().__init__(message)


TURN_FAILED_LLM_TIMEOUT = "TURN_FAILED_LLM_TIMEOUT"
TURN_FAILED_LLM_UNAVAILABLE = "TURN_FAILED_LLM_UNAVAILABLE"
TURN_FAILED_LLM_PROTOCOL = "TURN_FAILED_LLM_PROTOCOL"
TURN_FAILED_LLM_EMPTY = "TURN_FAILED_LLM_EMPTY"
TURN_FAILED_LLM_IDENTITY = "TURN_FAILED_LLM_IDENTITY"
