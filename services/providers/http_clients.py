"""Shared async HTTP clients for voice providers."""

from __future__ import annotations

import httpx

_shared: httpx.AsyncClient | None = None


def get_shared_async_client() -> httpx.AsyncClient:
    global _shared
    if _shared is None:
        _shared = httpx.AsyncClient(timeout=30.0)
    return _shared


async def close_shared_async_client() -> None:
    global _shared
    if _shared is not None:
        await _shared.aclose()
        _shared = None
