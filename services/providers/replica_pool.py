"""Replica pool: round-robin over worker URLs with failover.

ChatGPT-style serving in miniature: the same model behind N URLs, the
caller rotates across them and skips dead/saturated replicas. No new
infrastructure — replicas are the same worker.py on different ports.

A base URL string may be comma-separated ("http://h1:9101,http://h1:9111");
single URL keeps the exact old behavior (one-element pool, no failover).
"""

from __future__ import annotations

import threading
import weakref


class _ReplicaCursor:
    def __init__(self) -> None:
        self.index = 0
        self.lock = threading.Lock()


# Concurrent CallActors construct independent adapters. Share only routing
# rotation, never call/request/cancellation state. Obsolete configs expire
# when their last pool disappears; this is not a distributed load balancer.
_cursors: weakref.WeakValueDictionary[tuple[str, ...], _ReplicaCursor] = (
    weakref.WeakValueDictionary()
)
_cursors_lock = threading.Lock()


class FatalProviderError(Exception):
    """Non-retryable verdict (4xx other than 429/503) — do not fail over."""


class MidStreamUnavailable(Exception):
    """Failure after bytes were already yielded — retry would duplicate output."""


def split_urls(base_url: str) -> list[str]:
    urls = [u.strip().rstrip("/") for u in base_url.split(",")]
    urls = [u for u in urls if u]
    if not urls:
        raise ValueError("empty provider URL list")
    return urls


def is_retryable_status(status_code: int) -> bool:
    """Retry only saturation/rate signals — never model verdicts (422 etc.)."""
    return status_code in (429, 503)


class ReplicaPool:
    def __init__(self, base_urls: list[str]) -> None:
        if not base_urls:
            raise ValueError("replica pool needs at least one URL")
        self._urls = [u.rstrip("/") for u in base_urls]
        key = tuple(self._urls)
        with _cursors_lock:
            cursor = _cursors.get(key)
            if cursor is None:
                cursor = _ReplicaCursor()
                _cursors[key] = cursor
            self._cursor = cursor

    def __len__(self) -> int:
        return len(self._urls)

    @property
    def urls(self) -> list[str]:
        return list(self._urls)

    def order(self) -> list[str]:
        """Rotate first choice across live clients with the same configuration."""
        with self._cursor.lock:
            start = self._cursor.index % len(self._urls)
            self._cursor.index = (start + 1) % len(self._urls)
        return self._urls[start:] + self._urls[:start]
