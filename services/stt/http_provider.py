"""HTTP STT adapter — calls IMVERA_STT_URL; no fake transcripts."""

from __future__ import annotations

import time
from typing import Any

import httpx

from packages.contracts.enums import AsrQuality
from packages.contracts.providers import ProviderTimeout, ProviderUnavailable
from packages.contracts.stt import STTPartial, STTResult


class HttpSTTProvider:
    def __init__(self, base_url: str, timeout_s: float = 8.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    async def transcribe_partial(
        self,
        pcm_s16le: bytes,
        sample_rate: int,
        *,
        call_id: str,
        partial_id: str,
    ) -> STTPartial:
        return STTPartial(partial_id=partial_id, text="", is_final=False)

    async def transcribe_final(
        self,
        pcm_s16le: bytes,
        sample_rate: int,
        *,
        call_id: str,
        turn_id: int,
        deadline: float,
    ) -> STTResult:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderTimeout("STT deadline exceeded before request")
        try:
            async with httpx.AsyncClient(timeout=min(self._timeout_s, remaining)) as client:
                response = await client.post(
                    f"{self._base_url}/v1/transcribe",
                    json={
                        "call_id": call_id,
                        "turn_id": turn_id,
                        "sample_rate": sample_rate,
                        "pcm_b64": _b64(pcm_s16le),
                    },
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(str(exc)) from exc
        if response.status_code >= 400:
            raise ProviderUnavailable(f"STT HTTP {response.status_code}: {response.text[:200]}")
        data: dict[str, Any] = response.json()
        quality = _map_quality(data.get("asr_quality", "GOOD"))
        return STTResult(
            text=str(data.get("text", "")),
            asr_quality=quality,
            avg_logprob=data.get("avg_logprob"),
            no_speech_prob=data.get("no_speech_prob"),
        )


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


def _map_quality(raw: str) -> AsrQuality:
    upper = raw.upper()
    if upper == "LOW":
        return AsrQuality.LOW
    if upper == "UNUSABLE":
        return AsrQuality.UNUSABLE
    return AsrQuality.GOOD
