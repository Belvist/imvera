"""Asterisk lab helpers — NOT imported by production runtime."""

from __future__ import annotations

import httpx


def normalize_ari_http_root(url: str) -> str:
    return url.rstrip("/").removesuffix("/ari")


def ari_rest_base(http_root: str) -> str:
    return f"{normalize_ari_http_root(http_root)}/ari"


def _json_or_empty(response: httpx.Response) -> dict:
    if response.status_code == 204:
        return {}
    return response.json()
