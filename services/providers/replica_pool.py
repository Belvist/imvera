"""Replica pool: round-robin over worker URLs with failover.

ChatGPT-style serving in miniature: the same model behind N URLs, the
caller rotates across them and skips dead/saturated replicas. No new
infrastructure — replicas are the same worker.py on different ports.

A base URL string may be comma-separated ("http://h1:9101,http://h1:9111");
single URL keeps the exact old behavior (one-element pool, no failover).
"""

from __future__ import annotations

import threading


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
        self._idx = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._urls)

    @property
    def urls(self) -> list[str]:
        return list(self._urls)

    def order(self) -> list[str]:
        """URLs to try in order, starting point rotated per call."""
        with self._lock:
            start = self._idx % len(self._urls)
            self._idx += 1
        return self._urls[start:] + self._urls[:start]
