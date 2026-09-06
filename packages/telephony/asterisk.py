"""Minimal Asterisk ARI client for Stasis call setup."""

from __future__ import annotations

import os
from typing import Any

import httpx


class AsteriskARI:
    def __init__(
        self,
        base_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("IMVERA_ASTERISK_ARI_URL", "")).rstrip("/")
        self.user = user or os.environ.get("IMVERA_ASTERISK_ARI_USER", "imvera")
        self.password = password or os.environ.get("IMVERA_ASTERISK_ARI_PASSWORD", "")
        self._auth = (self.user, self.password)

    async def answer(self, channel_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(f"{self.base_url}/ari/channels/{channel_id}/answer")
            r.raise_for_status()
            return r.json()

    async def create_external_media(
        self,
        app: str,
        external_host: str,
        format: str = "slin16",
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/ari/channels/externalMedia",
                params={
                    "app": app,
                    "external_host": external_host,
                    "format": format,
                    "transport": "websocket",
                },
            )
            r.raise_for_status()
            return r.json()

    async def hangup(self, channel_id: str) -> None:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.delete(f"{self.base_url}/ari/channels/{channel_id}")
            if r.status_code not in (204, 404):
                r.raise_for_status()
