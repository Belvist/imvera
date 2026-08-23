"""Session store selection (Stage 6 + Phase 2 data core).

Rules change (DEGRADED, not silent fallback):
- No MOSS_REDIS_URL / MOSS_SESSION_STORE=memory  -> MemorySessionStore is the
  *configured* choice (single worker), degraded=False.
- Redis requested but unreachable -> MemorySessionStore with degraded=True and
  redis_requested=True. This is NEVER silent: it is logged loudly here and
  surfaced by Serve in /health. Postgres remains the source of truth for
  durable state, so the call path keeps working — but operators can see the
  cache is down.

The old behaviour (``build_session_store`` quietly returning a memory store
on a dead Redis as if nothing happened) is removed.
"""

import os


def _requested_redis():
    want = os.environ.get(
        "MOSS_SESSION_STORE",
        "redis" if os.environ.get("MOSS_REDIS_URL") else "memory",
    ).lower()
    return want == "redis"


def _maybe_session_store():
    """Return a SessionStore with ``.degraded`` and ``.redis_requested`` set.

    Raises nothing: the call path must never fail because of a cache. But an
    unreachable *requested* Redis is surfaced as degraded=True, not hidden.
    """
    if not _requested_redis():
        from moss_providers import MemorySessionStore

        store = MemorySessionStore(
            default_ttl_seconds=int(os.environ.get("MOSS_SESSION_TTL", "3600")))
        store.degraded = False
        store.redis_requested = False
        print("[call-agent] session store: memory (configured)", flush=True)
        return store

    from moss_providers import MemorySessionStore, RedisSessionStore

    try:
        store = RedisSessionStore()
        store.degraded = False
        store.redis_requested = True
        print("[call-agent] session store: redis", flush=True)
        return store
    except Exception as e:  # noqa: BLE001
        # DEGRADED: requested Redis is down. Postgres stays the truth; this
        # memory store is a process-local cache only. Surfaced in /health.
        store = MemorySessionStore(
            default_ttl_seconds=int(os.environ.get("MOSS_SESSION_TTL", "3600")))
        store.degraded = True
        store.redis_requested = True
        print(f"[call-agent] session store: DEGRADED — Redis requested but "
              f"unavailable ({e}); using process-local memory cache. "
              f"Sessions are NOT durable across workers/restarts. "
              f"Postgres remains the source of truth.", flush=True)
        return store