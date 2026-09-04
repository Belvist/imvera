#!/usr/bin/env python3
"""Prove continuous PCM ingress — frames arrive while user is still speaking.

Gate (Wave RT-1): pcm_frame timestamps BEFORE user_speech_end, not after
a completed WAV record cycle.

Usage:
    python3 scripts/prove_streaming_ingress.py
    python3 scripts/prove_streaming_ingress.py --ws   # optional live WebSocket feed

Exit 0 → STREAMING_INGRESS_PROVEN
Exit 1 → proof failed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import struct
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from voice_runtime.ingress_session import GatewayIngressSession
from voice_runtime.turn_detector import TunedEndpointPolicy
from voice_runtime.vad import SAMPLE_RATE
from voice_runtime.voice_gateway.server import VoiceGatewayServer

_CHUNK_SAMPLES = int(SAMPLE_RATE * 0.03)  # 30 ms @ 16 kHz


def _pcm_chunk(samples: list[int]) -> bytes:
    return struct.pack("<" + "h" * len(samples), *samples)


def _sine_chunk(amplitude: int = 6000, freq: float = 220.0, phase: float = 0.0) -> tuple[list[int], float]:
    out: list[int] = []
    for i in range(_CHUNK_SAMPLES):
        t = (phase + i) / SAMPLE_RATE
        out.append(int(amplitude * math.sin(2 * math.pi * freq * t)))
    return out, phase + _CHUNK_SAMPLES


def _silence_chunk() -> list[int]:
    return [0] * _CHUNK_SAMPLES


def simulate_utterance(
    *,
    speech_chunks: int = 12,
    silence_chunks: int = 28,
    endpoint_silence_ms: float = 700.0,
) -> GatewayIngressSession:
    """Feed synthetic speech then silence — mimics live PCM during talk."""
    session = GatewayIngressSession(
        call_id="prove-ingress",
        turn_detector=TunedEndpointPolicy(endpoint_silence_ms=endpoint_silence_ms),
    )
    phase = 0.0
    for _ in range(speech_chunks):
        chunk, phase = _sine_chunk(phase=phase)
        session.feed_pcm(_pcm_chunk(chunk))
    for _ in range(silence_chunks):
        session.feed_pcm(_pcm_chunk(_silence_chunk()))
    return session


def run_offline_proof() -> dict:
    session = simulate_utterance()
    status = session.prove_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return status


async def run_ws_proof(host: str, port: int) -> dict:
    try:
        import websockets
    except ImportError:
        raise SystemExit("websockets package required for --ws") from None

    gw = VoiceGatewayServer(host=host, port=port)
    frames: list[dict] = []

    def _on_frame(evt: dict) -> None:
        frames.append(evt)

    gw.on_pcm_frame = _on_frame
    gw.start_background()
    await asyncio.sleep(0.3)

    uri = f"ws://{host}:{port}/stream"
    phase = 0.0
    proof: dict = {"status": "STREAMING_INGRESS_PENDING"}

    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "hello", "call_id": "prove-ws"}))
        await ws.recv()

        for _ in range(12):
            chunk, phase = _sine_chunk(phase=phase)
            await ws.send(_pcm_chunk(chunk))
            await asyncio.sleep(0.02)

        for _ in range(28):
            await ws.send(_pcm_chunk(_silence_chunk()))
            await asyncio.sleep(0.02)

        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(msg)
                if data.get("type") == "turn":
                    proof = {
                        "status": (
                            "STREAMING_INGRESS_PROVEN"
                            if data.get("proof", {}).get("ok")
                            else "STREAMING_INGRESS_PENDING"
                        ),
                        "call_id": data.get("call_id"),
                        "proof": data.get("proof"),
                        "ws_frames_seen": len(frames),
                    }
                    break
        except asyncio.TimeoutError:
            proof = {
                "status": "STREAMING_INGRESS_PENDING",
                "reason": "turn_timeout",
                "ws_frames_seen": len(frames),
            }

    print(json.dumps(proof, ensure_ascii=False, indent=2))
    return proof


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove continuous PCM ingress")
    parser.add_argument("--ws", action="store_true", help="also run WebSocket proof")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9721)
    args = parser.parse_args()

    offline = run_offline_proof()
    ok = offline.get("status") == "STREAMING_INGRESS_PROVEN"

    if args.ws:
        ws_result = asyncio.run(run_ws_proof(args.host, args.port))
        ok = ok and ws_result.get("status") == "STREAMING_INGRESS_PROVEN"

    if ok:
        print("\n✓ STREAMING_INGRESS_PROVEN", file=sys.stderr)
        return 0
    print("\n✗ STREAMING_INGRESS_PENDING", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
