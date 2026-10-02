"""HTTP STT adapter — calls IMVERA_STT_URL; no fake transcripts.

base_url may be comma-separated: replicas are tried round-robin with
failover on transport errors and 429/503 (never on model verdicts).
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from typing import Any

import httpx
from pydantic import ValidationError

from packages.contracts.enums import AsrQuality
from packages.contracts.providers import (
    ProviderCancelled,
    ProviderInvalidOutput,
    ProviderTimeout,
    ProviderUnavailable,
)
from packages.contracts.stt import (
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
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("STT timeout_s must be finite and positive")
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
        try:
            return STTCapabilities.model_validate(_response_object(response))
        except ValidationError as exc:
            raise ProviderInvalidOutput("Invalid STT capabilities") from exc

    async def _post_with_client(
        self, client: httpx.AsyncClient, url: str, path: str,
        body: dict[str, Any], timeout: float,
    ) -> httpx.Response:
        try:
            # httpx bounds individual network phases, not the complete request.
            # A slowly trickling worker must not exceed the actor's turn budget.
            async with asyncio.timeout(timeout):
                return await client.post(f"{url}{path}", json=body, timeout=timeout)
        except (asyncio.CancelledError, httpx.TimeoutException, TimeoutError) as exc:
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
            if isinstance(exc, TimeoutError):
                raise httpx.ReadTimeout("STT request budget exceeded") from exc
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
        data = _response_object(response)
        if (data.get("request_id") != body["request_id"]
                or data.get("partial_id") != partial_id
                or data.get("is_final") is not False
                or data.get("partial_mode") != "prefix_batch"):
            raise ProviderInvalidOutput("STT preview identity/mode/finality mismatch")
        _validate_transcript_fields(data)
        try:
            return STTPartial.model_validate(data)
        except ValidationError as exc:
            raise ProviderInvalidOutput("Invalid STT preview schema") from exc

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
        if not math.isfinite(deadline):
            raise ProviderTimeout("STT deadline must be finite")
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
            if response.status_code == 499:
                raise ProviderCancelled("STT final cancelled")
            if response.status_code >= 400:
                raise ProviderUnavailable(
                    f"STT HTTP {response.status_code}: {response.text[:200]}"
                )
            break
        else:
            if time.monotonic() >= deadline:
                raise ProviderTimeout("STT deadline exceeded") from last_error
            raise last_error or ProviderUnavailable("STT: all replicas failed")
        data = _response_object(response)
        if data.get("is_final", True) is not True:
            raise ProviderInvalidOutput("STT final endpoint returned a non-final result")
        if data.get("request_id", body["request_id"]) != body["request_id"]:
            raise ProviderInvalidOutput("STT final request identity mismatch")
        _validate_transcript_fields(data)
        # Old worker responses may omit quality. Missing evidence is unusable,
        # never an invented GOOD signal for the post-STT decision gate.
        quality = _map_quality(data.get("asr_quality", "UNUSABLE"))
        try:
            return STTResult.model_validate({
                **data,
                "raw_text": data.get("raw_text") or data["text"],
                "asr_quality": quality,
                "audio_quality": {"rms": data.get("pcm_rms")},
            })
        except ValidationError as exc:
            raise ProviderInvalidOutput("Invalid STT final schema") from exc


def _response_object(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProviderInvalidOutput("STT response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ProviderInvalidOutput("STT response must be a JSON object")
    return data


def _validate_transcript_fields(data: dict[str, Any]) -> None:
    if not isinstance(data.get("text"), str) or len(data["text"]) > 16000:
        raise ProviderInvalidOutput("STT text must be a bounded string")
    if data.get("raw_text") is not None and (
        not isinstance(data["raw_text"], str) or len(data["raw_text"]) > 16000
    ):
        raise ProviderInvalidOutput("STT raw_text must be a bounded string")
    for field in ("duration_ms", "pcm_rms", "avg_logprob", "no_speech_prob"):
        value = data.get(field)
        if value is None:
            continue
        if (isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value)):
            raise ProviderInvalidOutput(f"STT {field} must be a finite number")
        if field in {"duration_ms", "pcm_rms", "no_speech_prob"} and value < 0:
            raise ProviderInvalidOutput(f"STT {field} must be nonnegative")
        if field == "no_speech_prob" and value > 1:
            raise ProviderInvalidOutput("STT no_speech_prob exceeds one")
    critical_terms = data.get("critical_terms", [])
    if isinstance(critical_terms, list):
        for item in critical_terms:
            value = item.get("logprob") if isinstance(item, dict) else None
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value)
            ):
                raise ProviderInvalidOutput("STT critical logprob must be a finite number")
    word_probs = data.get("word_probs", [])
    if isinstance(word_probs, list):
        for value in word_probs:
            if (isinstance(value, bool) or not isinstance(value, (float, int))
                    or not math.isfinite(value) or not 0 <= value <= 1):
                raise ProviderInvalidOutput("STT word probability must be between zero and one")


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


def _map_quality(raw: str) -> AsrQuality:
    if not isinstance(raw, str):
        raise ProviderInvalidOutput("STT asr_quality must be a string")
    upper = raw.upper()
    if upper == "LOW":
        return AsrQuality.LOW
    if upper == "UNUSABLE":
        return AsrQuality.UNUSABLE
    if upper == "GOOD":
        return AsrQuality.GOOD
    raise ProviderInvalidOutput("Unknown STT asr_quality")
