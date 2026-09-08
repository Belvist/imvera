"""Minimal PJSUA2 transport gate — REGISTER, INVITE 7000, RTP, WAV I/O, hangup."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tools.pjsua2_blackbox_caller.client import Pjsua2ImportError, Pjsua2SipClient
from tools.pjsua2_blackbox_caller.config import load_pjsua2_config

ROOT = Path(__file__).resolve().parents[2]
GATE_ROOT = ROOT / ".run" / "pjsua2_transport_gate"


@dataclass
class TransportGateResult:
    passed: bool = False
    sip_registered: bool = False
    sip_confirmed: bool = False
    rtp_tx_packets: int = 0
    rtp_rx_packets: int = 0
    caller_downlink_bytes: int = 0
    offered_codecs: list[str] = field(default_factory=list)
    negotiated_codec: str = ""
    negotiated_clock_rate: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_transport_gate() -> TransportGateResult:
    """Phase B step 1 — no DialogueEngine acceptance."""
    result = TransportGateResult()
    cfg = load_pjsua2_config()
    result.offered_codecs = list(cfg.offered_codecs)

    try:
        client = Pjsua2SipClient(cfg.blackbox)
    except Pjsua2ImportError as exc:
        result.errors.append(str(exc))
        return result
    except NotImplementedError as exc:
        result.errors.append(str(exc))
        return result

    result.errors.append("PJSUA2 transport gate not implemented yet — wire AudioMedia next")
    return result


def main() -> int:
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = run_transport_gate()
    out = GATE_ROOT / "transport_gate_result.json"
    out.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    label = "PASS" if result.passed else "FAIL"
    print(f"PJSUA2_TRANSPORT_GATE = {label} ({time.time() - started:.1f}s)", flush=True)
    if not result.passed:
        for err in result.errors:
            print(f"  {err}", flush=True)
        print(f"  artifact: {out}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
