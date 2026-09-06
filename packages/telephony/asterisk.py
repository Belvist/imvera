"""Minimal Asterisk ARI client for Stasis call setup."""

from __future__ import annotations

import os
from typing import Any

import httpx


def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


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
            return _json_or_empty(r)

    async def create_bridge(self, bridge_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/ari/bridges",
                json={"type": "mixing", "bridgeId": bridge_id},
            )
            if r.status_code == 409:
                return {"id": bridge_id}
            r.raise_for_status()
            return _json_or_empty(r)

    async def add_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/ari/bridges/{bridge_id}/addChannel",
                params={"channel": channel_id},
            )
            r.raise_for_status()

    async def snoop_channel(
        self,
        channel_id: str,
        app: str,
        spy: str = "in",
        whisper: str = "none",
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/ari/channels/{channel_id}/snoop",
                params={"app": app, "spy": spy, "whisper": whisper},
            )
            r.raise_for_status()
            return _json_or_empty(r)

    async def create_external_media(
        self,
        app: str,
        connection_id: str,
        *,
        direction: str = "both",
        format: str = "slin16",
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/ari/channels/externalMedia",
                params={
                    "app": app,
                    "external_host": connection_id,
                    "transport": "websocket",
                    "encapsulation": "none",
                    "format": format,
                    "direction": direction,
                    "connection_type": "client",
                },
            )
            r.raise_for_status()
            return _json_or_empty(r)

    async def hangup(self, channel_id: str) -> None:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.delete(f"{self.base_url}/ari/channels/{channel_id}")
            if r.status_code not in (204, 404):
                r.raise_for_status()

    async def destroy_bridge(self, bridge_id: str) -> None:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.delete(f"{self.base_url}/ari/bridges/{bridge_id}")
            if r.status_code not in (204, 404):
                r.raise_for_status()
