"""HTTP STT adapter — calls IMVERA_STT_URL; no fake transcripts.

base_url may be comma-separated: replicas are tried round-robin with
failover on transport errors and 429/503 (never on model verdicts).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

import httpx

from packages.contracts.enums import AsrQuality
from packages.contracts.providers import (
    ProviderCancelled,
    ProviderInvalidOutput,
    ProviderTimeout,
    ProviderUnavailable,
)
from packages.contracts.stt import (
    AudioQualityHints,
    CriticalTermMatch,
    STTCapabilities,
    STTPartial,
    STTResult,
)
from services.providers.replica_pool import ReplicaPool, is_retryable_status, split_urls

_log = logging.getLogger("providers.stt")


class HttpSTTProvider:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 8.0,
        client: httpx.AsyncClient | None = None,
        prefix_previews: bool = False,
    ) -> None:
        self._base_url = base_url
        self._pool = ReplicaPool(split_urls(base_url))
        self._timeout_s = timeout_s
        self._client = client
        self._prefix_previews = prefix_previews

    async def capabilities(self) -> STTCapabilities:
        """Inspect the selected replica; never assume batch ASR is streaming."""
        url = self._pool.urls[0]
        if self._client is not None:
            response = await self._client.get(f"{url}/v1/capabilities", timeout=2.0)
        else:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{url}/v1/capabilities")
        response.raise_for_status()
        return STTCapabilities.model_validate(response.json())

    async def _post_with_client(
        self, client: httpx.AsyncClient, url: str, path: str,
        body: dict[str, Any], timeout: float,
    ) -> httpx.Response:
        try:
            return await client.post(f"{url}{path}", json=body, timeout=timeout)
        except (asyncio.CancelledError, httpx.TimeoutException):
            # Best effort only. Running PyTorch may finish, but its result is
            # invalidated on both ends; the actor never waits here to endpoint.
            try:
                await asyncio.wait_for(
                    client.post(f"{url}/v1/cancel", json={"request_id": body["request_id"]},
                                timeout=0.2),
                    timeout=0.25,
                )
            except (httpx.HTTPError, TimeoutError):
                _log.warning("STT cancel acknowledgement unavailable call_id=%s", body["call_id"])
            raise

    async def _post(
        self, url: str, path: str, body: dict[str, Any], timeout: float,
    ) -> httpx.Response:
        if self._client is not None:
            return await self._post_with_client(self._client, url, path, body, timeout)
        async with httpx.AsyncClient() as client:
            return await self._post_with_client(client, url, path, body, timeout)

    async def transcribe_partial(
        self,
        pcm_s16le: bytes,
        sample_rate: int,
        *,
        call_id: str,
        partial_id: str,
    ) -> STTPartial:
        if not self._prefix_previews:
            raise ProviderUnavailable(
                "Current STT adapter is final-only; partial transcription is unsupported"
            )
        body = {
            "request_id": f"stt-{uuid.uuid4().hex}",
            "call_id": call_id,
            "partial_id": partial_id,
            "sample_rate": sample_rate,
            "pcm_b64": _b64(pcm_s16le),
            "timeout_s": 2.0,
        }
        # Optional work is never retried across replicas: do not multiply load.
        try:
            response = await self._post(self._pool.urls[0], "/v1/preview", body, 2.0)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"STT preview unavailable: {exc}") from exc
        if response.status_code == 499:
            raise ProviderCancelled("STT preview cancelled")
        if response.status_code >= 400:
            raise ProviderUnavailable(f"STT preview HTTP {response.status_code}")
        data = response.json()
        if (data.get("request_id") != body["request_id"]
                or data.get("partial_id") != partial_id
                or data.get("is_final") is not False
                or data.get("partial_mode") != "prefix_batch"):
            raise ProviderInvalidOutput("STT preview identity/mode/finality mismatch")
        return STTPartial.model_validate(data)

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
            "request_id": f"stt-{uuid.uuid4().hex}",
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
                # Each attempt gets a fresh cancellation identity and a server
                # relative budget (not a foreign host's monotonic timestamp).
                body["request_id"] = f"stt-{uuid.uuid4().hex}"
                body["timeout_s"] = min(self._timeout_s, remaining, 60.0)
                response = await self._post(
                    url, "/v1/transcribe", body, body["timeout_s"],
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
        if data.get("is_final", True) is not True:
            raise ProviderInvalidOutput("STT final endpoint returned a non-final result")
        if data.get("request_id", body["request_id"]) != body["request_id"]:
            raise ProviderInvalidOutput("STT final request identity mismatch")
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
