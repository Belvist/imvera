"""Core integration — persistence stores."""

import os

from packages.contracts.core import CallRecordStore
from packages.core.memory_store import (
    InMemoryCallRecordStore,
    observation_from_fact,
    observation_from_risk,
)
from packages.core.pg_store import PostgresCallRecordStore


def create_call_record_store(dsn: str | None = None) -> CallRecordStore:
    url = dsn or os.environ.get("IMVERA_PG_URL")
    if url:
        return PostgresCallRecordStore(url)
    return InMemoryCallRecordStore()


__all__ = [
    "CallRecordStore",
    "InMemoryCallRecordStore",
    "PostgresCallRecordStore",
    "create_call_record_store",
    "observation_from_fact",
    "observation_from_risk",
]
