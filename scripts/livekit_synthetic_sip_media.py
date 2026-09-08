#!/usr/bin/env python3
"""Synthetic SIP caller for LiveKit media gate — transport proof only."""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE_DIR = ROOT / ".run" / "livekit-gate"
INVITE_META = GATE_DIR / "synthetic_invite.json"
FRAME_BYTES = 160  # 20 ms @ 8 kHz u8
SILENCE_BYTE = 0x80
PYVOIP_VERSION = "1.6.8"


def _require_pyvoip() -> None:
    try:
        import audioop_lts  # noqa: F401
    except ImportError:
        try:
            import audioop  # noqa: F401
        except ImportError:
            print("BLOCKED: pip install -e '.[sip-lab]'", file=sys.stderr)
            raise SystemExit(1) from None
    try:
        import pyVoIP  # noqa: F401
    except ImportError:
        print(f"BLOCKED: pyVoIP=={PYVOIP_VERSION} required", file=sys.stderr)
        raise SystemExit(1)


def _preflight_udp_port(port: int) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise RuntimeError(f"Synthetic SIP local port {port} in use") from exc
    finally:
        probe.close()


def generate_tone_u8(
    *,
    frequency_hz: float = 440.0,
    duration_s: float = 3.0,
    sample_rate: int = 8000,
    amplitude: int = 100,
) -> bytes:
    samples = int(sample_rate * duration_s)
    out = bytearray(samples)
    for i in range(samples):
        value = 127 + int(amplitude * math.sin(2.0 * math.pi * frequency_hz * i / sample_rate))
        out[i] = max(0, min(255, value))
    return bytes(out)


def _write_invite_meta(payload: dict) -> None:
    GATE_DIR.mkdir(parents=True, exist_ok=True)
    INVITE_META.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_synthetic_call(
    *,
    sip_host: str,
    sip_port: int,
    dial_number: str,
    local_sip_port: int,
    speech_seconds: float,
) -> dict:
    from pyVoIP.VoIP import CallState, VoIPPhone

    caller_pcm = generate_tone_u8(duration_s=speech_seconds)
    _preflight_udp_port(local_sip_port)
    public_ip = os.environ.get("LIVEKIT_NODE_IP", "127.0.0.1")

    phone = VoIPPhone(
        sip_host,
        sip_port,
        "media-gate-caller",
        "",
        myIP=public_ip,
        sipPort=local_sip_port,
        rtpPortLow=14000,
        rtpPortHigh=14100,
    )
    phone.start()
    time.sleep(1.0)

    invite_sent_at = time.time()
    _write_invite_meta(
        {
            "invite_sent_at": invite_sent_at,
            "dial_number": dial_number,
            "sip_host": sip_host,
            "sip_port": sip_port,
            "negotiated_codecs": ["PCMU"],
        }
    )

    call = phone.call(dial_number)
    answered_at: float | None = None
    rtp_packets = 0
    rtp_bytes = 0

    try:
        for _ in range(60):
            if call.state == CallState.ANSWERED:
                answered_at = time.time()
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("SIP INVITE not answered within 15s")

        _write_invite_meta(
            {
                "invite_sent_at": invite_sent_at,
                "sip_answered_at": answered_at,
                "dial_number": dial_number,
                "sip_host": sip_host,
                "sip_port": sip_port,
                "negotiated_codecs": ["PCMU"],
            }
        )

        silence = bytes([SILENCE_BYTE]) * FRAME_BYTES * 10
        for chunk in (silence, caller_pcm, silence):
            for offset in range(0, len(chunk), FRAME_BYTES):
                frame = chunk[offset : offset + FRAME_BYTES]
                call.write_audio(frame)
                rtp_packets += 1
                rtp_bytes += len(frame)
                time.sleep(0.02)

        time.sleep(2.0)
    finally:
        try:
            call.hangup()
        except Exception:
            pass
        phone.stop()

    _write_invite_meta(
        {
            "invite_sent_at": invite_sent_at,
            "sip_answered_at": answered_at,
            "dial_number": dial_number,
            "sip_host": sip_host,
            "sip_port": sip_port,
            "negotiated_codecs": ["PCMU"],
            "sip_rtp_tx_packets": rtp_packets,
            "sip_rtp_tx_bytes": rtp_bytes,
        }
    )
    return {
        "invite_sent_at": invite_sent_at,
        "sip_answered_at": answered_at,
        "sip_rtp_tx_packets": rtp_packets,
        "sip_rtp_tx_bytes": rtp_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic SIP caller for LiveKit media gate")
    parser.add_argument("--sip-host", default=os.environ.get("LIVEKIT_SIP_HOST", "127.0.0.1"))
    parser.add_argument("--sip-port", type=int, default=int(os.environ.get("LIVEKIT_SIP_PORT", "5060")))
    parser.add_argument(
        "--dial",
        default=os.environ.get("LIVEKIT_SIP_INBOUND_NUMBER", "+15550001000"),
    )
    parser.add_argument(
        "--local-sip-port",
        type=int,
        default=int(os.environ.get("IMVERA_LIVEKIT_SYNTH_SIP_PORT", "5076")),
    )
    parser.add_argument("--speech-seconds", type=float, default=3.0)
    args = parser.parse_args()

    _require_pyvoip()
    try:
        result = run_synthetic_call(
            sip_host=args.sip_host,
            sip_port=args.sip_port,
            dial_number=args.dial,
            local_sip_port=args.local_sip_port,
            speech_seconds=args.speech_seconds,
        )
    except Exception as exc:
        print(f"livekit-synthetic-sip-media: FAILED {exc}", file=sys.stderr)
        return 1

    print(
        "livekit-synthetic-sip-media: OK "
        f"rtp_tx_packets={result['sip_rtp_tx_packets']} "
        f"rtp_tx_bytes={result['sip_rtp_tx_bytes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
