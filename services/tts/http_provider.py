"""HTTP TTS adapter — streams PCM from IMVERA_TTS_URL."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import AsyncIterator

import httpx

from packages.contracts.providers import AudioChunk, ProviderTimeout, ProviderUnavailable


class HttpTTSProvider:
    def __init__(self, base_url: str, timeout_s: float = 12.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._cancelled: set[str] = set()

    async def cancel(self, generation_id: str) -> None:
        self._cancelled.add(generation_id)
        try:
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
            async with httpx.AsyncClient(timeout=min(self._timeout_s, remaining)) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/v1/synthesize",
                    json={
                        "text": text,
                        "generation_id": generation_id,
                        "phrase_id": phrase_id,
                        "sample_rate": 16000,
                    },
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise ProviderUnavailable(
                            f"TTS HTTP {response.status_code}: {body[:200]!r}"
                        )
                    seq = 0
                    async for line in response.aiter_lines():
                        if generation_id in self._cancelled:
                            break
                        if not line:
                            continue
                        data = json.loads(line)
                        pcm = base64.b64decode(data["pcm_b64"])
                        yield AudioChunk(
                            pcm_s16le=pcm,
                            sample_rate=int(data.get("sample_rate", 16000)),
                            sequence=seq,
                            is_last=bool(data.get("is_last", False)),
                        )
                        seq += 1
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(str(exc)) from exc
