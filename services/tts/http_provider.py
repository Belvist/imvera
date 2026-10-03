"""HTTP TTS adapter — streams PCM from IMVERA_TTS_URL.

base_url may be comma-separated: replicas are tried round-robin with
failover before the first audio chunk (never after — yielded audio
cannot be un-yielded). Cancel is broadcast to all replicas.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import AsyncIterator

import httpx

from packages.contracts.providers import (
    AudioChunk,
    ProviderCancelled,
    ProviderTimeout,
    ProviderUnavailable,
)
from services.providers.replica_pool import (
    FatalProviderError,
    MidStreamUnavailable,
    ReplicaPool,
    is_retryable_status,
    split_urls,
)

_log = logging.getLogger("providers.tts")


class HttpTTSProvider:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 12.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._pool = ReplicaPool(split_urls(base_url))
        self._timeout_s = timeout_s
        self._client = client
        self._cancelled: set[str] = set()

    async def cancel(self, generation_id: str) -> None:
        self._cancelled.add(generation_id)
        for url in self._pool.urls:
            try:
                if self._client is not None:
                    await self._client.post(
                        f"{url}/v1/cancel",
                        json={"generation_id": generation_id},
                        timeout=2.0,
                    )
                else:
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        await client.post(
                            f"{url}/v1/cancel",
                            json={"generation_id": generation_id},
                        )
            except httpx.HTTPError:
                pass

    async def synthesize(
        self,
        text: str,
        *,
        call_id: str,
        generation_id: str,
        phrase_id: str,
        deadline: float,
    ) -> AsyncIterator[AudioChunk]:
        if generation_id in self._cancelled:
            return
        last_error: Exception | None = None
        for url in self._pool.order():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderTimeout("TTS deadline exceeded before request")
            try:
                async for chunk in self._stream_from(
                    url, text, call_id, generation_id, phrase_id, deadline
                ):
                    yield chunk
                return
            except (FatalProviderError, ProviderCancelled, MidStreamUnavailable):
                raise
            except ProviderUnavailable as exc:
                last_error = exc
                _log.warning("TTS failover call_id=%s: %s", call_id, exc)
                continue
        raise last_error or ProviderUnavailable("TTS: all replicas failed")

    async def _stream_from(
        self,
        url: str,
        text: str,
        call_id: str,
        generation_id: str,
        phrase_id: str,
        deadline: float,
    ) -> AsyncIterator[AudioChunk]:
        yielded = False
        try:
            async for chunk in self._iter_stream(
                url, text, call_id, generation_id, phrase_id, deadline
            ):
                yielded = True
                yield chunk
        except ProviderUnavailable as exc:
            if yielded:
                raise MidStreamUnavailable(
                    f"{url}: mid-stream failure after audio yield"
                ) from exc
            raise

    async def _iter_stream(
        self,
        url: str,
        text: str,
        call_id: str,
        generation_id: str,
        phrase_id: str,
        deadline: float,
    ) -> AsyncIterator[AudioChunk]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderTimeout("TTS deadline exceeded before request")
        try:
            # MLX first chunk can exceed 12s after worker restart; read timeout must cover it.
            read_timeout = max(self._timeout_s, remaining, 45.0)
            timeout = httpx.Timeout(5.0, read=read_timeout)
            if self._client is not None:
                client = self._client
                owned = False
            else:
                client = httpx.AsyncClient(timeout=timeout)
                owned = True
            try:
                async with client.stream(
                    "POST",
                    f"{url}/v1/synthesize",
                    json={
                        "call_id": call_id,
                        "text": text,
                        "generation_id": generation_id,
                        "phrase_id": phrase_id,
                        "sample_rate": 16000,
                        "timeout_ms": max(1, int(remaining * 1000)),
                    },
                    timeout=timeout,
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        err = ProviderUnavailable(
                            f"TTS HTTP {response.status_code}: {body[:200]!r}"
                        )
                        if is_retryable_status(response.status_code):
                            raise err
                        raise FatalProviderError(str(err)) from err
                    seq = 0
                    async for line in response.aiter_lines():
                        if generation_id in self._cancelled:
                            raise ProviderCancelled(generation_id)
                        if not line:
                            continue
                        data = json.loads(line)
                        if data.get("done"):
                            if data.get("cancelled"):
                                raise ProviderCancelled(generation_id)
                            if data.get("error"):
                                raise ProviderUnavailable(str(data["error"]))
                            return
                        if "pcm_b64" not in data:
                            continue
                        pcm = base64.b64decode(data["pcm_b64"])
                        if not pcm and data.get("is_last"):
                            return
                        yield AudioChunk(
                            pcm_s16le=pcm,
                            sample_rate=int(data.get("sample_rate", 16000)),
                            sequence=seq,
                            is_last=bool(data.get("is_last", False)),
                        )
                        seq += 1
                    raise ProviderUnavailable("TTS stream ended without completion marker")
            finally:
                if owned:
                    await client.aclose()
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{url}: {exc}") from exc
