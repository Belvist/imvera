"""Inference preflight — block call session when STT/TTS/LLM are down."""

from __future__ import annotations

import httpx


async def inference_blockers(
    stt_url: str,
    tts_url: str,
    llm_url: str,
    *,
    timeout_s: float = 2.0,
) -> list[str]:
    blockers: list[str] = []
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        for name, base in (("stt", stt_url), ("tts", tts_url), ("llm", llm_url)):
            try:
                response = await client.get(f"{base.rstrip('/')}/health/ready")
                if response.status_code != 200:
                    detail = response.text[:200]
                    blockers.append(f"{name}: HTTP {response.status_code} {detail}")
            except httpx.HTTPError as exc:
                blockers.append(f"{name}: {exc}")
    return blockers
