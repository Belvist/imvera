#!/usr/bin/env python3
"""P0-A-EXTERNAL gate — synthetic SIP/RTP from Mac host through Docker published ports."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE_ROOT = ROOT / ".run" / "freeswitch-gate"
EXTERNAL_REPORT = GATE_ROOT / "p0a_external_report.json"


def _require_fs_running() -> None:
    proc = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "imvera-freeswitch"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stdout.strip() != "true":
        print("BLOCKED: imvera-freeswitch container not running", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    from scripts.local_sip_config import detect_media_host

    _require_fs_running()
    host = detect_media_host()
    GATE_ROOT.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["FS_SIP_HOST"] = host
    env["FS_SIP_PORT"] = "5060"
    env["FS_INBOUND_NUMBER"] = os.environ.get("FS_INBOUND_NUMBER", "+15550001000")
    env["IMVERA_FS_SYNTH_SIP_PORT"] = os.environ.get("IMVERA_FS_SYNTH_SIP_PORT", "5077")
    env["FS_NODE_IP"] = host

    print(f"p0a-external-gate: host synthetic → {host}:5060 dial={env['FS_INBOUND_NUMBER']}")
    print("  path: Mac LAN → Docker published UDP/TCP → FreeSWITCH container")

    synth = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "freeswitch_synthetic_sip_media.py")],
        cwd=ROOT,
        env=env,
        check=False,
    )
    if synth.returncode != 0:
        report = {
            "gate": "p0a-external",
            "status": "FAIL",
            "phase": "synthetic_sip",
            "sip_host": host,
            "detail": "host synthetic caller failed before media gate",
        }
        EXTERNAL_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return synth.returncode

    gate = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "freeswitch_media_gate.py")],
        cwd=ROOT,
        check=False,
    )

    invite_meta = {}
    invite_path = GATE_ROOT / "synthetic_invite.json"
    if invite_path.is_file():
        invite_meta = json.loads(invite_path.read_text(encoding="utf-8"))

    report = {
        "gate": "p0a-external",
        "status": "PASS" if gate.returncode == 0 else "FAIL",
        "sip_host": host,
        "dial_number": env["FS_INBOUND_NUMBER"],
        "docker_published_rtp": "16384-16484/udp",
        "synthetic": invite_meta,
        "media_gate_rc": gate.returncode,
        "note": (
            "Proves Mac host → Docker published ports → FS. "
            "Does NOT replace live Zoiper forensic boundary."
        ),
    }
    EXTERNAL_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return gate.returncode


if __name__ == "__main__":
    raise SystemExit(main())
