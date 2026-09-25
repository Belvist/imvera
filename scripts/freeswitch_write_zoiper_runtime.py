#!/usr/bin/env python3
"""Write FreeSWITCH runtime config for Zoiper on Mac (LAN RTP + bridge WS)."""

from __future__ import annotations

from pathlib import Path

from scripts.local_sip_config import detect_media_host

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "infra" / "freeswitch" / "conf" / "generated"


def write_zoiper_runtime_config(media_host: str | None = None) -> Path:
    host = media_host or detect_media_host()
    GEN.mkdir(parents=True, exist_ok=True)

    vars_path = GEN / "vars_imvera.runtime.xml"
    vars_path.write_text(
        "\n".join(
            [
                "<include>",
                '  <X-PRE-PROCESS cmd="set" data="imvera_media_bridge_ws=ws://host.docker.internal:9210/stream"/>',
                f'  <X-PRE-PROCESS cmd="set" data="domain={host}"/>',
                f'  <X-PRE-PROCESS cmd="set" data="domain_name={host}"/>',
                f'  <X-PRE-PROCESS cmd="set" data="external_rtp_ip={host}"/>',
                f'  <X-PRE-PROCESS cmd="set" data="external_sip_ip={host}"/>',
                "</include>",
                "",
            ]
        ),
        encoding="utf-8",
    )

    sip_path = GEN / "internal.zoiper-voice.xml"
    sip_path.write_text(
        "\n".join(
            [
                '<profile name="internal">',
                "  <domains>",
                '    <domain name="all" alias="true" parse="false"/>',
                "  </domains>",
                "  <settings>",
                '    <param name="context" value="public"/>',
                '    <param name="auth-calls" value="false"/>',
                '    <param name="auth-all-packets" value="false"/>',
                '    <param name="rtp-ip" value="0.0.0.0"/>',
                '    <param name="sip-ip" value="0.0.0.0"/>',
                f'    <param name="ext-rtp-ip" value="{host}"/>',
                f'    <param name="ext-sip-ip" value="{host}"/>',
                # Same-LAN Zoiper lab: do NOT rewrite Contact to WAN "received"
                # IP (breaks answer/RTP — Contact becomes 185.x and 7000 hangs).
                '    <param name="NDLB-received-in-nat-reg-contact" value="false"/>',
                '    <param name="aggressive-nat-detection" value="false"/>',
                # P0 plan 3e: explicit capacity (lab values; raise after soak).
                '    <param name="max-sessions" value="30"/>',
                '    <param name="sessions-per-second" value="10"/>',
                # Zoiper lab: G722 wideband first (HD voice), G711 fallback.
                '    <param name="inbound-codec-prefs" value="G722,PCMU,PCMA"/>',
                '    <param name="outbound-codec-prefs" value="G722,PCMU,PCMA"/>',
                "  </settings>",
                "</profile>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return vars_path


def main() -> int:
    path = write_zoiper_runtime_config()
    host = detect_media_host()
    print(f"freeswitch runtime: media_host={host} vars={path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
