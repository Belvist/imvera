#!/usr/bin/env python3
"""Collect one Zoiper/FreeSWITCH call forensic bundle — RTP vs READ vs WS boundary."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORENSIC_ROOT = ROOT / ".run" / "freeswitch-forensic"
CONTAINER = "imvera-freeswitch"


def _docker_fs_cli(command: str) -> str:
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "fs_cli", "-x", command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "fs_cli failed")
    return result.stdout


def _copy_container_file(container_path: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["docker", "cp", f"{CONTAINER}:{container_path}", str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and dest.is_file()


def main() -> int:
    parser = argparse.ArgumentParser(description="FreeSWITCH media forensic collector")
    parser.add_argument("fs_uuid", help="FreeSWITCH channel UUID")
    parser.add_argument("--call-id", default="", help="CallActor call_id (fs-xxxxxxxx)")
    args = parser.parse_args()

    from packages.telephony.freeswitch_forensics import (
        analyze_wav_pcm,
        classify_media_boundary,
        evidence_from_channel_vars,
        parse_uuid_dump,
    )

    fs_uuid = args.fs_uuid.strip()
    call_id = args.call_id.strip() or f"fs-{fs_uuid[:8]}"
    out_dir = FORENSIC_ROOT / call_id
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        dump_text = _docker_fs_cli(f"uuid_dump {fs_uuid}")
    except RuntimeError as exc:
        print(f"BLOCKED: uuid_dump failed: {exc}", file=sys.stderr)
        return 1

    (out_dir / "uuid_dump.txt").write_text(dump_text, encoding="utf-8")
    vars_map = parse_uuid_dump(dump_text)
    evidence = evidence_from_channel_vars(fs_uuid, vars_map, call_id=call_id)

    read_container = f"/var/imvera/forensic/{fs_uuid}_read.wav"
    read_host = out_dir / "fs_read_leg.wav"
    if _copy_container_file(read_container, read_host):
        evidence.fs_read_wav = str(read_host.relative_to(ROOT))
        try:
            evidence.fs_read_rms_peak, evidence.fs_read_nonzero_frames = analyze_wav_pcm(read_host)
        except wave.Error:
            pass

    from packages.telephony.freeswitch_forensics import (
        DOCKER_PUBLISHED_RTP_RANGE,
        port_in_published_range,
    )

    evidence.docker_published_rtp_range = DOCKER_PUBLISHED_RTP_RANGE
    if evidence.local_media_port and not port_in_published_range(evidence.local_media_port):
        print(
            f"WARN: local_media_port={evidence.local_media_port} outside Docker publish "
            f"{DOCKER_PUBLISHED_RTP_RANGE}",
            file=sys.stderr,
        )

    ws_candidates = [
        ROOT / ".run" / "freeswitch-gate" / call_id / "raw_inbound.wav",
        out_dir / "ws_raw_inbound.wav",
    ]
    for path in ws_candidates:
        if path.is_file():
            evidence.ws_raw_wav = str(path.relative_to(ROOT))
            evidence.ws_rms_peak, evidence.ws_nonzero_frames = analyze_wav_pcm(path)
            break

    trace_path = ROOT / ".run" / "traces" / f"{call_id}.jsonl"
    if trace_path.is_file():
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("type") != "stage.timing":
                continue
            payload = row.get("payload") or {}
            if payload.get("stage") == "media.pipeline":
                evidence.ws_rx_frames = int(payload.get("actor_pcm_frames") or 0)
                evidence.ws_rx_bytes = int(payload.get("actor_pcm_bytes") or 0)
                evidence.actor_nonzero_frames = int(payload.get("nonzero_pcm_frames") or 0)
            if payload.get("stage") == "uplink.summary":
                evidence.listen_rms_peak = float(payload.get("listen_rms_peak") or 0.0)

    evidence = classify_media_boundary(evidence)
    report_path = out_dir / "forensic.json"
    report_path.write_text(
        json.dumps(evidence.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        f"  rtp_local={vars_map.get('local_media_ip', '')}:{vars_map.get('local_media_port', '')}"
    )
    print(
        f"  rtp_remote={vars_map.get('remote_media_ip', '')}"
        f":{vars_map.get('remote_media_port', '')}"
    )
    print(f"boundary={evidence.boundary}")
    print(f"detail={evidence.boundary_detail}")
    print(f"rtp_in_packets={evidence.rtp_audio_in_packets}")
    print(f"rtp_in_bytes={evidence.rtp_audio_in_bytes}")
    print(f"codec={evidence.negotiated_codec}")
    print(f"fs_read_rms={evidence.fs_read_rms_peak:.1f} nonzero={evidence.fs_read_nonzero_frames}")
    print(f"ws_rms={evidence.ws_rms_peak:.1f} nonzero={evidence.ws_nonzero_frames}")
    print(
        f"actor_nonzero={evidence.actor_nonzero_frames} listen_rms={evidence.listen_rms_peak:.1f}"
    )
    print(f"report={report_path}")
    return 0 if evidence.boundary == "ok_chain" else 2


if __name__ == "__main__":
    raise SystemExit(main())
