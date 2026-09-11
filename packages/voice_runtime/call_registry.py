"""Product CallBinding handoff — shared CallRecordStore persistence (not conversation state).

Process-local dicts are NOT product handoff: voice_service and imvera_media_bridge
are separate processes. Production uses the same Postgres-backed CallRecordStore
(call_results.metadata). InMemory is for tests only (optionally with an explicit
shared backend dict to simulate two processes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.contracts.core import CallRecordStore

PRODUCT_BINDING_META_KEY = "product_call_binding"


@dataclass(frozen=True)
class CallBinding:
    """Small product handoff contract — NOT DialogueEngine / conversation state."""

    call_id: str
    family_id: str
    person_id: str = ""
    elder_name: str = ""
    transport: str = "browser"
    mission: dict[str, Any] | None = None
    mission_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "family_id": self.family_id,
            "person_id": self.person_id,
            "elder_name": self.elder_name,
            "transport": self.transport,
            "mission": self.mission,
            "mission_id": self.mission_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> CallBinding:
        meta = raw.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        mission = raw.get("mission")
        if mission is not None and not isinstance(mission, dict):
            mission = None
        return cls(
            call_id=str(raw.get("call_id") or ""),
            family_id=str(raw.get("family_id") or ""),
            person_id=str(raw.get("person_id") or ""),
            elder_name=str(raw.get("elder_name") or ""),
            transport=str(raw.get("transport") or "browser"),
            mission=mission,
            mission_id=str(raw.get("mission_id") or ""),
            metadata=dict(meta),
        )


class CallRegistry:
    """Store-backed CallBinding registry. Conversation state stays on CallActor/DialogueEngine."""

    def __init__(self, store: CallRecordStore) -> None:
        self._store = store

    @property
    def store(self) -> CallRecordStore:
        return self._store

    def register(self, binding: CallBinding) -> CallBinding:
        result = self._store.put_call_binding(binding.to_payload())
        if not result.ok:
            raise RuntimeError(f"call binding persist failed: {result.error}")
        return binding

    def bind_fs_uuid(self, call_id: str, fs_uuid: str) -> CallBinding | None:
        binding = self.get(call_id)
        if binding is None:
            return None
        meta = dict(binding.metadata)
        meta["fs_uuid"] = fs_uuid
        updated = CallBinding(
            call_id=binding.call_id,
            family_id=binding.family_id,
            person_id=binding.person_id,
            elder_name=binding.elder_name,
            transport=binding.transport,
            mission=binding.mission,
            mission_id=binding.mission_id,
            metadata=meta,
        )
        self.register(updated)
        return updated

    def get(self, call_id: str) -> CallBinding | None:
        if not call_id:
            return None
        payload = self._store.get_call_binding(call_id)
        if not payload:
            return None
        return CallBinding.from_payload(payload)

    def family_id_for(self, call_id: str) -> str | None:
        binding = self.get(call_id)
        return binding.family_id if binding else None

    def resolve(
        self,
        *,
        call_id: str | None = None,
        fs_uuid: str | None = None,
    ) -> CallBinding | None:
        if call_id:
            found = self.get(call_id)
            if found is not None:
                return found
        if fs_uuid:
            by_uuid = self._store.get_call_binding_by_fs_uuid(fs_uuid)
            if by_uuid:
                return CallBinding.from_payload(by_uuid)
            # Accept product call_id passed as stream path segment.
            return self.get(fs_uuid)
        return None

    def pop(self, call_id: str) -> CallBinding | None:
        binding = self.get(call_id)
        if binding is None:
            return None
        self._store.delete_call_binding(call_id)
        return binding

    def clear(self) -> None:
        """Test helper — clears product bindings when the store supports it."""
        clearer = getattr(self._store, "clear_call_bindings", None)
        if callable(clearer):
            clearer()


def build_call_registry(store: CallRecordStore) -> CallRegistry:
    """Construct a registry bound to a CallRecordStore (shared PG in production)."""
    return CallRegistry(store)


# Back-compat for tests that imported get_call_registry — NOT a product singleton.
# Prefer build_call_registry(store) so two processes do not share Python globals.
def get_call_registry(store: CallRecordStore | None = None) -> CallRegistry:
    if store is None:
        from packages.core import create_call_record_store

        store = create_call_record_store()
    return CallRegistry(store)
