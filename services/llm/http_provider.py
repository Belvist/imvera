"""HTTP client for LLM interpret/render workers."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from packages.contracts.providers import ProviderTimeout, ProviderUnavailable
from packages.contracts.semantic import SemanticPayload, TurnContext, TurnInterpretation


class HttpLLMProvider:
    def __init__(self, base_url: str, timeout_s: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    async def interpret_turn(
        self, context: TurnContext, *, deadline: float
    ) -> TurnInterpretation:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderTimeout("LLM deadline exceeded")
        try:
            async with httpx.AsyncClient(timeout=min(self._timeout_s, remaining)) as client:
                response = await client.post(
                    f"{self._base_url}/v1/interpret",
                    json={"context": context.model_dump(mode="json")},
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(str(exc)) from exc
        if response.status_code >= 400:
            raise ProviderUnavailable(f"LLM HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        payload = SemanticPayload.model_validate(data["payload"])
        return TurnInterpretation(
            context=context,
            payload=payload,
            provider_request_id=data.get("provider_request_id", data.get("request_id", "")),
        )

    async def render_text(self, action: dict[str, Any], facts: list[dict], deadline: float) -> str:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderTimeout("render deadline exceeded")
        async with httpx.AsyncClient(timeout=min(self._timeout_s, remaining)) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/v1/render",
                json={
                    "action": action,
                    "facts": facts,
                    "capabilities": {"persistence": True, "family_delivery": False},
                },
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise ProviderUnavailable(f"render HTTP {response.status_code}: {body!r}")
                text = ""
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    item = json.loads(line)
                    if item.get("text"):
                        text = item["text"]
                return text.strip()
