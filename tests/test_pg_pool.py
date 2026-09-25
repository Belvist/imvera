"""PG connection pool: parallel persists share bounded connections (P0 plan 3a)."""

from __future__ import annotations

import os
import threading

import pytest

from packages.core.pg_store import PostgresCallRecordStore

PG_URL = os.environ.get("IMVERA_PG_URL")


def _pg_available() -> bool:
    if not PG_URL:
        return False
    try:
        import psycopg

        with psycopg.connect(PG_URL, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL not available")


def test_pool_opens_lazily_and_reuses_connections() -> None:
    store = PostgresCallRecordStore(PG_URL, max_size=4)
    try:
        assert store.pool_stats() == {"opened": False}
        errors: list[str] = []

        def worker(i: int) -> None:
            try:
                result = store.ensure_call(f"pool-t{i}", "pool-fam")
                if not result.ok:
                    errors.append(str(result.error))
            except Exception as exc:  # noqa: BLE001 — must surface, not hang
                errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert not any(t.is_alive() for t in threads), "pool must not hang"
        assert errors == [], errors
        stats = store.pool_stats()
        assert stats["opened"] is True
        assert stats["connections_num"] <= 4
        assert stats["requests_num"] >= 20
    finally:
        store.close()


def test_pool_exhaustion_is_error_not_hang() -> None:
    store = PostgresCallRecordStore(PG_URL, min_size=1, max_size=1)
    try:
        held = store._pool_or_open().connection()
        with held:
            result = store.ensure_call("pool-x", "pool-fam")
            assert result.ok is False
            assert result.error, "exhaustion must carry an explicit error"
    finally:
        store.close()
