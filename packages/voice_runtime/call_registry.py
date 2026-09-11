"""Durable product-call binding: call_id → family/mission (not conversation state).

Used so POST /v1/calls can hand the SAME mission_id to FreeSWITCH media bridge
without a second dialogue brain or live `_sessions` dependency.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CallBinding:
    call_id: str
    family_id: str
    person_id: str = ""
    elder_name: str = ""
    transport: str = "browser"
    mission: dict[str, Any] | None = None
    mission_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class CallRegistry:
    """Process-local durable map. Conversation state remains CallActor/DialogueEngine only."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_call: dict[str, CallBinding] = {}
        self._by_fs_uuid: dict[str, str] = {}

    def register(self, binding: CallBinding) -> CallBinding:
        with self._lock:
            self._by_call[binding.call_id] = binding
            return binding

    def bind_fs_uuid(self, call_id: str, fs_uuid: str) -> CallBinding | None:
        with self._lock:
            binding = self._by_call.get(call_id)
            if binding is None:
                return None
            self._by_fs_uuid[fs_uuid] = call_id
            return binding

    def get(self, call_id: str) -> CallBinding | None:
        with self._lock:
            return self._by_call.get(call_id)

    def family_id_for(self, call_id: str) -> str | None:
        with self._lock:
            binding = self._by_call.get(call_id)
            return binding.family_id if binding else None

    def resolve(
        self,
        *,
        call_id: str | None = None,
        fs_uuid: str | None = None,
    ) -> CallBinding | None:
        with self._lock:
            if call_id and call_id in self._by_call:
                return self._by_call[call_id]
            if fs_uuid:
                mapped = self._by_fs_uuid.get(fs_uuid)
                if mapped:
                    return self._by_call.get(mapped)
                # Accept product call_id passed as fs stream path segment.
                if fs_uuid in self._by_call:
                    return self._by_call[fs_uuid]
            return None

    def pop(self, call_id: str) -> CallBinding | None:
        with self._lock:
            binding = self._by_call.pop(call_id, None)
            if binding is None:
                return None
            stale = [k for k, v in self._by_fs_uuid.items() if v == call_id]
            for k in stale:
                self._by_fs_uuid.pop(k, None)
            return binding

    def clear(self) -> None:
        with self._lock:
            self._by_call.clear()
            self._by_fs_uuid.clear()


_REGISTRY = CallRegistry()


def get_call_registry() -> CallRegistry:
    return _REGISTRY
