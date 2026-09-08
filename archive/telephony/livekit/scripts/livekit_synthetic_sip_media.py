#!/usr/bin/env python3
"""Synthetic SIP caller for LiveKit media gate — 440 Hz uplink + downlink capture."""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE_DIR = ROOT / ".run" / "livekit-gate"
INVITE_META = GATE_DIR / "synthetic_invite.json"
DOWNLINK_U8 = GATE_DIR / "synthetic_downlink.u8"
FRAME_BYTES = 160  # 20 ms @ 8 kHz u8
SILENCE_BYTE = 0x80
CALLER_TONE_HZ = 440.0
PROBE_OUTBOUND_HZ = 880.0
PROBE_WAIT_S = float(os.environ.get("IMVERA_LIVEKIT_PROBE_WAIT_S", "8.0"))
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
    frequency_hz: float = CALLER_TONE_HZ,
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


class _DownlinkTap:
    def __init__(self) -> None:
        self._buf = bytearray()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def peek(self) -> bytes:
        return bytes(self._buf)

    def start(self, call) -> None:
        def _loop() -> None:
            while not self._stop.is_set() and len(self._buf) < 8000 * 30:
                try:
                    chunk = call.read_audio(FRAME_BYTES, blocking=True)
                except (IndexError, Exception):
                    time.sleep(0.01)
                    continue
                if chunk:
                    self._buf.extend(chunk)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> bytes:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        return bytes(self._buf)


def _downlink_has_probe_tone(buf: bytes, sample_rate: int = 8000) -> bool:
    if len(buf) < sample_rate // 5:
        return False
    sys.path.insert(0, str(ROOT))
    from packages.telephony.livekit_gate_tone import tone_present

    window = buf[-sample_rate:]
    samples = [float(b - 128) for b in window]
    present, _ = tone_present(samples, sample_rate, PROBE_OUTBOUND_HZ, min_snr=6.0)
    return present


def _wait_for_imvera_probe(call, tap: _DownlinkTap, timeout_s: float) -> bool:
    """Send silence until caller hears IMVERA 880 Hz probe (or timeout)."""
    silence = bytes([SILENCE_BYTE]) * FRAME_BYTES
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        call.write_audio(silence)
        time.sleep(0.02)
        if _downlink_has_probe_tone(tap.peek()):
            return True
    return False


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
    if DOWNLINK_U8.exists():
        DOWNLINK_U8.unlink()
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
            "caller_tone_hz": CALLER_TONE_HZ,
            "probe_outbound_hz": PROBE_OUTBOUND_HZ,
            "negotiated_codecs": ["PCMU"],
        }
    )

    call = phone.call(dial_number)
    answered_at: float | None = None
    rtp_packets = 0
    rtp_bytes = 0
    downlink = b""
    probe_heard = False

    try:
        for _ in range(60):
            if call.state == CallState.ANSWERED:
                answered_at = time.time()
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("SIP INVITE not answered within 15s")

        tap = _DownlinkTap()
        tap.start(call)

        probe_heard = _wait_for_imvera_probe(call, tap, PROBE_WAIT_S)
        if not probe_heard:
            print(
                f"livekit-synthetic-sip-media: probe {PROBE_OUTBOUND_HZ} Hz not detected "
                f"within {PROBE_WAIT_S}s — sending caller tone anyway",
                file=sys.stderr,
            )

        silence = bytes([SILENCE_BYTE]) * FRAME_BYTES * 5
        for chunk in (silence, caller_pcm, silence):
            for offset in range(0, len(chunk), FRAME_BYTES):
                frame = chunk[offset : offset + FRAME_BYTES]
                call.write_audio(frame)
                rtp_packets += 1
                rtp_bytes += len(frame)
                time.sleep(0.02)

        time.sleep(3.0)
        downlink = tap.stop()
    finally:
        try:
            call.hangup()
        except Exception:
            pass
        phone.stop()

    GATE_DIR.mkdir(parents=True, exist_ok=True)
    if downlink:
        DOWNLINK_U8.write_bytes(downlink)

    meta = {
        "invite_sent_at": invite_sent_at,
        "sip_answered_at": answered_at,
        "dial_number": dial_number,
        "sip_host": sip_host,
        "sip_port": sip_port,
        "caller_tone_hz": CALLER_TONE_HZ,
        "probe_outbound_hz": PROBE_OUTBOUND_HZ,
        "probe_heard_before_uplink": probe_heard,
        "negotiated_codecs": ["PCMU"],
        "synthetic_rtp_tx_packets": rtp_packets,
        "synthetic_rtp_tx_bytes": rtp_bytes,
        "synthetic_downlink_bytes": len(downlink),
        "synthetic_downlink_path": str(DOWNLINK_U8),
    }
    _write_invite_meta(meta)
    return meta


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
        f"synthetic_rtp_tx_packets={result['synthetic_rtp_tx_packets']} "
        f"downlink_bytes={result['synthetic_downlink_bytes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
