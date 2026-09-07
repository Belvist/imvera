"""HTTP TTS adapter — streams PCM from IMVERA_TTS_URL."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import AsyncIterator

import httpx

from packages.contracts.providers import (
    AudioChunk,
    ProviderCancelled,
    ProviderTimeout,
    ProviderUnavailable,
)


class HttpTTSProvider:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 12.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client
        self._cancelled: set[str] = set()

    async def cancel(self, generation_id: str) -> None:
        self._cancelled.add(generation_id)
        try:
            if self._client is not None:
                await self._client.post(
                    f"{self._base_url}/v1/cancel",
                    json={"generation_id": generation_id},
                    timeout=2.0,
                )
            else:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    await client.post(
                        f"{self._base_url}/v1/cancel",
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
                    f"{self._base_url}/v1/synthesize",
                    json={
                        "call_id": call_id,
                        "text": text,
                        "generation_id": generation_id,
                        "phrase_id": phrase_id,
                        "sample_rate": 16000,
                    },
                    timeout=timeout,
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise ProviderUnavailable(
                            f"TTS HTTP {response.status_code}: {body[:200]!r}"
                        )
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
            finally:
                if owned:
                    await client.aclose()
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(str(exc)) from exc
