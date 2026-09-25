"""HTTP client for LLM interpret/render workers."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from packages.contracts.providers import ProviderTimeout, ProviderUnavailable
from packages.contracts.semantic import SemanticPayload, TurnContext, TurnInterpretation
from services.providers.replica_pool import (
    FatalProviderError,
    MidStreamUnavailable,
    ReplicaPool,
    is_retryable_status,
    split_urls,
)

_log = logging.getLogger("providers.llm")


class RenderChunk:
    __slots__ = ("text", "delta", "done")

    def __init__(self, text: str, *, delta: bool = False, done: bool = False) -> None:
        self.text = text
        self.delta = delta
        self.done = done


class HttpLLMProvider:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._pool = ReplicaPool(split_urls(base_url))
        self._timeout_s = timeout_s
        self._client = client

    def _remaining_timeout(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderTimeout("LLM deadline exceeded")
        return min(self._timeout_s, remaining)

    async def cancel_request(self, request_id: str) -> None:
        # Broadcast: after failover the working replica is unknown, and a
        # stale generation must never speak (P0 G-15).
        for url in self._pool.urls:
            try:
                if self._client is not None:
                    await self._client.post(
                        f"{url}/v1/cancel",
                        json={"request_id": request_id},
                        timeout=2.0,
                    )
                else:
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        await client.post(
                            f"{url}/v1/cancel",
                            json={"request_id": request_id},
                        )
            except httpx.HTTPError:
                pass

    async def interpret_turn(
        self,
        context: TurnContext,
        *,
        deadline: float,
        request_id: str | None = None,
    ) -> TurnInterpretation:
        last_error: Exception | None = None
        for url in self._pool.order():
            remaining = self._remaining_timeout(deadline)
            rid = request_id or f"req-{uuid.uuid4().hex[:12]}"
            timeout_ms = max(1, int(remaining * 1000))
            body = {
                "context": context.model_dump(mode="json"),
                "request_id": rid,
                "timeout_ms": timeout_ms,
            }
            owned_client: httpx.AsyncClient | None = None
            if self._client is not None:
                client = self._client
            else:
                owned_client = httpx.AsyncClient(timeout=self._remaining_timeout(deadline))
                client = owned_client
            try:
                response = await client.post(f"{url}/v1/interpret", json=body)
            except httpx.HTTPError as exc:
                last_error = ProviderUnavailable(f"{url}: {exc}")
                _log.warning("LLM failover call_id=%s: %s", context.call_id, last_error)
                continue
            finally:
                if owned_client is not None:
                    closer = getattr(owned_client, "aclose", None)
                    if closer is not None:
                        await closer()
            if is_retryable_status(response.status_code):
                last_error = ProviderUnavailable(
                    f"LLM HTTP {response.status_code} at {url}"
                )
                _log.warning("LLM failover call_id=%s: %s", context.call_id, last_error)
                continue
            if response.status_code >= 400:
                raise ProviderUnavailable(
                    f"LLM HTTP {response.status_code}: {response.text[:300]}"
                )
            break
        else:
            raise last_error or ProviderUnavailable("LLM: all replicas failed")
        data = response.json()
        payload = SemanticPayload.model_validate(data["payload"])
        return TurnInterpretation(
            context=context,
            payload=payload,
            provider_request_id=data.get("provider_request_id", data.get("request_id", rid)),
        )

    async def render_stream(
        self,
        action: dict[str, Any],
        facts: list[dict],
        deadline: float,
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[RenderChunk]:
        last_error: Exception | None = None
        for url in self._pool.order():
            remaining = self._remaining_timeout(deadline)
            rid = request_id or f"req-{uuid.uuid4().hex[:12]}"
            timeout_ms = max(1, int(remaining * 1000))
            try:
                async for chunk in self._render_from(url, action, facts, rid, timeout_ms):
                    yield chunk
                return
            except (FatalProviderError, MidStreamUnavailable):
                raise
            except ProviderUnavailable as exc:
                last_error = exc
                _log.warning("LLM render failover: %s", exc)
                continue
        raise last_error or ProviderUnavailable("LLM render: all replicas failed")

    async def _render_from(
        self,
        url: str,
        action: dict[str, Any],
        facts: list[dict],
        rid: str,
        timeout_ms: int,
    ) -> AsyncIterator[RenderChunk]:
        remaining = self._remaining_timeout(time.monotonic() + timeout_ms / 1000)
        owned_client: httpx.AsyncClient | None = None
        if self._client is not None:
            client = self._client
        else:
            owned_client = httpx.AsyncClient(timeout=remaining)
            client = owned_client
        yielded = False
        try:
            async with client.stream(
                "POST",
                f"{url}/v1/render",
                json={
                    "action": action,
                    "facts": facts,
                    "capabilities": {"persistence": True, "family_delivery": False},
                    "request_id": rid,
                    "timeout_ms": timeout_ms,
                },
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    err = ProviderUnavailable(
                        f"render HTTP {response.status_code}: {body!r}"
                    )
                    if is_retryable_status(response.status_code):
                        raise err
                    raise FatalProviderError(str(err)) from err
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    item = json.loads(line)
                    if item.get("done"):
                        yield RenderChunk(str(item.get("text", "")).strip(), done=True)
                        return
                    if item.get("delta") and item.get("text"):
                        yielded = True
                        yield RenderChunk(str(item["text"]), delta=True)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{url}: {exc}") from exc
        except ProviderUnavailable as exc:
            if yielded:
                raise MidStreamUnavailable(f"{url}: mid-stream render failure") from exc
            raise
        finally:
            if owned_client is not None:
                closer = getattr(owned_client, "aclose", None)
                if closer is not None:
                    await closer()

    async def render_text(
        self,
        action: dict[str, Any],
        facts: list[dict],
        deadline: float,
        *,
        request_id: str | None = None,
    ) -> str:
        parts: list[str] = []
        async for chunk in self.render_stream(
            action, facts, deadline, request_id=request_id
        ):
            if chunk.delta:
                parts.append(chunk.text)
            elif chunk.done and chunk.text:
                return chunk.text
        return "".join(parts).strip()
