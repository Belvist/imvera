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
    store: CallRecordStore
    if url:
        store = PostgresCallRecordStore(url)
    else:
        store = InMemoryCallRecordStore()
    spool_dir = os.environ.get("IMVERA_PERSIST_SPOOL_DIR")
    if spool_dir:
        from packages.core.spill import SpillingCallRecordStore

        store = SpillingCallRecordStore(store, spool_dir)
    return store


__all__ = [
    "CallRecordStore",
    "InMemoryCallRecordStore",
    "PostgresCallRecordStore",
    "create_call_record_store",
    "observation_from_fact",
    "observation_from_risk",
]
