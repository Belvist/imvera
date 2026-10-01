"""HTTP STT adapter — calls IMVERA_STT_URL; no fake transcripts.

base_url may be comma-separated: replicas are tried round-robin with
failover on transport errors and 429/503 (never on model verdicts).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from packages.contracts.enums import AsrQuality
from packages.contracts.providers import ProviderTimeout, ProviderUnavailable
from packages.contracts.stt import AudioQualityHints, CriticalTermMatch, STTPartial, STTResult
from services.providers.replica_pool import ReplicaPool, is_retryable_status, split_urls

_log = logging.getLogger("providers.stt")


class HttpSTTProvider:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 8.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._pool = ReplicaPool(split_urls(base_url))
        self._timeout_s = timeout_s
        self._client = client

    async def transcribe_partial(
        self,
        pcm_s16le: bytes,
        sample_rate: int,
        *,
        call_id: str,
        partial_id: str,
    ) -> STTPartial:
        raise ProviderUnavailable(
            "Current STT adapter is final-only; partial transcription is unsupported"
        )

    async def transcribe_final(
        self,
        pcm_s16le: bytes,
        sample_rate: int,
        *,
        call_id: str,
        turn_id: int,
        deadline: float,
        utterance_id: str = "",
    ) -> STTResult:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderTimeout("STT deadline exceeded before request")
        body = {
            "call_id": call_id,
            "turn_id": turn_id,
            "utterance_id": utterance_id,
            "sample_rate": sample_rate,
            "pcm_b64": _b64(pcm_s16le),
        }
        last_error: Exception | None = None
        for url in self._pool.order():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderTimeout("STT deadline exceeded before request")
            try:
                if self._client is not None:
                    response = await self._client.post(
                        f"{url}/v1/transcribe",
                        json=body,
                        timeout=min(self._timeout_s, remaining),
                    )
                else:
                    async with httpx.AsyncClient(
                        timeout=min(self._timeout_s, remaining)
                    ) as client:
                        response = await client.post(
                            f"{url}/v1/transcribe",
                            json=body,
                        )
            except httpx.HTTPError as exc:
                last_error = ProviderUnavailable(f"{url}: {exc}")
                _log.warning("STT failover call_id=%s: %s", call_id, last_error)
                continue
            if is_retryable_status(response.status_code):
                last_error = ProviderUnavailable(
                    f"STT HTTP {response.status_code} at {url}: "
                    f"{response.text[:200]}"
                )
                _log.warning("STT failover call_id=%s: %s", call_id, last_error)
                continue
            if response.status_code >= 400:
                raise ProviderUnavailable(
                    f"STT HTTP {response.status_code}: {response.text[:200]}"
                )
            break
        else:
            raise last_error or ProviderUnavailable("STT: all replicas failed")
        data: dict[str, Any] = response.json()
        quality = _map_quality(data.get("asr_quality", "GOOD"))
        critical_raw = data.get("critical_terms") or []
        critical_terms = [
            CriticalTermMatch(
                term=str(item.get("term", "")),
                matched=bool(item.get("matched", False)),
                logprob=item.get("logprob"),
            )
            for item in critical_raw
            if isinstance(item, dict)
        ]
        return STTResult(
            text=str(data.get("text", "")),
            raw_text=str(data.get("raw_text") or data.get("text", "")),
            duration_ms=int(data.get("duration_ms") or 0) or None,
            model_revision=str(data.get("model_revision") or "") or None,
            asr_quality=quality,
            avg_logprob=data.get("avg_logprob"),
            no_speech_prob=data.get("no_speech_prob"),
            critical_terms=critical_terms,
            audio_quality=AudioQualityHints(
                rms=float(data.get("pcm_rms") or 0) or None,
            ),
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
