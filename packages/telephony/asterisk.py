"""Minimal Asterisk ARI client for Stasis call setup."""

from __future__ import annotations

import os
from typing import Any

import httpx


def normalize_ari_http_root(url: str) -> str:
    """Return Asterisk HTTP root without trailing /ari (e.g. http://host:8088)."""
    root = url.rstrip("/")
    if root.endswith("/ari"):
        return root[: -len("/ari")]
    return root


def ari_rest_base(url: str) -> str:
    return f"{normalize_ari_http_root(url)}/ari"


def ari_events_ws_url(http_root: str, user: str, password: str, app: str) -> str:
    base = ari_rest_base(http_root)
    ws = base.replace("http://", "ws://").replace("https://", "wss://")
    return f"{ws}/events?api_key={user}:{password}&app={app}"


def is_stasis_app_registered(
    http_root: str,
    auth: tuple[str, str],
    app_name: str,
    *,
    timeout: float = 3.0,
) -> bool:
    try:
        r = httpx.get(f"{ari_rest_base(http_root)}/applications", auth=auth, timeout=timeout)
        if r.status_code != 200:
            return False
        payload = r.json()
        if not isinstance(payload, list):
            return False
        return any(isinstance(item, dict) and item.get("name") == app_name for item in payload)
    except httpx.HTTPError:
        return False


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
        raw = base_url or os.environ.get("IMVERA_ASTERISK_ARI_URL", "http://127.0.0.1:8088")
        self.http_root = normalize_ari_http_root(raw)
        self.base_url = ari_rest_base(raw)
        self.user = user or os.environ.get("IMVERA_ASTERISK_ARI_USER", "imvera")
        self.password = password or os.environ.get("IMVERA_ASTERISK_ARI_PASSWORD", "")
        self._auth = (self.user, self.password)

    async def answer(self, channel_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(f"{self.base_url}/channels/{channel_id}/answer")
            r.raise_for_status()
            return _json_or_empty(r)

    async def create_bridge(self, bridge_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/bridges",
                json={"type": "mixing", "bridgeId": bridge_id},
            )
            if r.status_code == 409:
                return {"id": bridge_id}
            r.raise_for_status()
            return _json_or_empty(r)

    async def add_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/bridges/{bridge_id}/addChannel",
                params={"channel": channel_id},
            )
            r.raise_for_status()

    async def snoop_channel(
        self,
        channel_id: str,
        app: str | None = None,
        *,
        spy: str = "in",
        whisper: str = "none",
    ) -> dict[str, Any]:
        params: dict[str, str] = {"spy": spy, "whisper": whisper}
        if app:
            params["app"] = app
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/channels/{channel_id}/snoop",
                params=params,
            )
            r.raise_for_status()
            return _json_or_empty(r)

    async def get_channel_variable(self, channel_id: str, variable: str) -> str:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.get(
                f"{self.base_url}/channels/{channel_id}/variable",
                params={"variable": variable},
            )
            r.raise_for_status()
            payload = _json_or_empty(r)
            return str(payload.get("value", ""))

    async def create_external_media(
        self,
        app: str,
        connection_id: str,
        *,
        format: str = "slin16",
        direction: str = "both",
        connection_type: str = "client",
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/channels/externalMedia",
                params={
                    "app": app,
                    "external_host": connection_id,
                    "transport": "websocket",
                    "encapsulation": "none",
                    "format": format,
                    "direction": direction,
                    "connection_type": connection_type,
                    "transport_data": "f(json)",
                },
            )
            r.raise_for_status()
            return _json_or_empty(r)

    async def hangup(self, channel_id: str) -> None:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.delete(f"{self.base_url}/channels/{channel_id}")
            if r.status_code not in (204, 404):
                r.raise_for_status()

    async def destroy_bridge(self, bridge_id: str) -> None:
        async with httpx.AsyncClient(auth=self._auth, timeout=10.0) as client:
            r = await client.delete(f"{self.base_url}/bridges/{bridge_id}")
            if r.status_code not in (204, 404):
                r.raise_for_status()
