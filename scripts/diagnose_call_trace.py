#!/usr/bin/env python3
"""Diagnose live call trace — speak/hear failure patterns (sip-31365 / sip-97e9)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACES = ROOT / ".run" / "traces"

_WELLNESS_WORDS = re.compile(
    r"\b(хорошо|нормально|не\s+очень|плохо|отлично|да)\b",
    re.I,
)
_GARBAGE_STT = frozenset({"ответ", "пять вы", "сд", "сейчас"})


def _load_trace(path: Path) -> tuple[list[dict], list[str], list[dict]]:
    """Return stage payloads, top-level event types, and raw rows from JSONL trace."""
    stages: list[dict] = []
    event_types: list[str] = []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append(row)
        event_type = str(row.get("type", ""))
        if event_type:
            event_types.append(event_type)
        payload = row.get("payload") or row.get("data") or {}
        if isinstance(payload, dict) and payload.get("stage"):
            stages.append(payload)
        elif event_type == "stage_timing" and isinstance(payload, dict):
            stages.append(payload)
    return stages, event_types, rows


def _stage_names(stages: list[dict]) -> list[str]:
    return [str(s.get("stage", "")) for s in stages]


def _stt_texts(rows: list[dict], stages: list[dict]) -> list[str]:
    texts: list[str] = []
    for row in rows:
        if row.get("type") == "stt.final":
            payload = row.get("payload") or {}
            text = str(payload.get("text", "")).strip()
            if text:
                texts.append(text)
    for stage in stages:
        if stage.get("stage") == "stt.final":
            # stage rows may not carry text; skip duplicates
            pass
    return texts


def _normalize_key(text: str) -> str:
    return re.sub(r"[^\wа-яё]+", "", text.strip().casefold())


def _verdict(
    *,
    cap_bytes: int,
    cap_rms: float,
    listen_peaks: list[float],
    stt_texts: list[str],
    echo_discarded: int,
) -> str:
    if cap_bytes == 0:
        return "CAPTURE_DEAD"
    if cap_rms < 120:
        return "CAPTURE_QUIET"
    if not listen_peaks or max(listen_peaks) < 120:
        return "VAD_DEAF"
    if not stt_texts:
        return "STT_MISSING"
    if any(_normalize_key(t) in _GARBAGE_STT for t in stt_texts):
        return "STT_GARBAGE"
    if not any(_WELLNESS_WORDS.search(t) for t in stt_texts) and echo_discarded == 0:
        return "STT_GARBAGE"
    if any(_WELLNESS_WORDS.search(t) for t in stt_texts):
        return "OK_WELLNESS_HEARD"
    return "DIALOGUE_REJECT"


def diagnose(call_id: str) -> int:
    path = TRACES / f"{call_id}.jsonl"
    if not path.exists():
        print(f"Trace not found: {path}", file=sys.stderr)
        return 1

    stages, event_types, rows = _load_trace(path)
    names = _stage_names(stages)
    unique = list(dict.fromkeys(names))

    print(f"Call: {call_id}")
    print(f"Trace: {path}")
    print(f"Stages ({len(names)} events, {len(unique)} unique):\n")
    for name in unique:
        print(f"  - {name}")

    print("\n--- Checks ---")
    has_playback_done = (
        "playback.completed" in event_types
        or "playback.completed" in names
        or any(n.endswith("playback.completed") for n in names)
    )
    has_listen = "listen.enabled" in names
    has_speech = "speech.started" in event_types or any(n.startswith("speech.") for n in names)
    has_stt = "stt.final" in event_types or "stt.final" in names
    interrupted = "playback.interrupted" in event_types or "playback.interrupted" in names

    if interrupted:
        print("FAIL: playback.interrupted — greeting/TTS cut (echo / barge-in class)")
    if not has_playback_done and not interrupted:
        print("FAIL: no playback.completed — Vera may not have finished speaking")
    elif has_playback_done:
        print("OK: playback.completed present")

    if has_playback_done and not has_listen:
        print("FAIL: playback.completed but NO listen.enabled — stuck mute (sip-97e9 class)")
    elif has_listen:
        print("OK: listen.enabled present")

    if has_listen and not has_speech:
        print(
            "WARN: listen.enabled but no speech.* — mic/VAD/capture (check uplink/capture.summary)"
        )
    elif has_speech:
        print("OK: speech events present")

    if has_speech and not has_stt:
        print("WARN: speech but no stt.final — STT path issue")
    elif has_stt:
        print("OK: stt.final present")

    listen_peaks: list[float] = []
    cap_bytes = 0
    cap_rms = 0.0
    echo_discarded = sum(1 for s in stages if s.get("stage") == "stt.echo_discarded")

    for stage in stages:
        if stage.get("stage") == "uplink.summary":
            peak = float(stage.get("listen_rms_peak", 0))
            bytes_ = int(stage.get("listen_uplink_bytes", 0))
            blocked = int(stage.get("listen_blocked_bytes", 0))
            listen_peaks.append(peak)
            print(
                f"\nuplink.summary: listen_rms_peak={peak}, "
                f"listen_uplink_bytes={bytes_}, listen_blocked_bytes={blocked}"
            )
            if peak < 120 and bytes_ > 0:
                print("  → likely VAD threshold / quiet mic (RMS low but bytes flowing)")
            elif bytes_ == 0:
                print("  → no uplink during listen window — capture dead or still muted")
        if stage.get("stage") == "listen.enabled":
            print(
                f"\nlisten.enabled: half_duplex={stage.get('lab_half_duplex')} "
                f"echo_ref={stage.get('echo_ref_gate')} "
                f"opening_always_listen={stage.get('opening_always_listen')} "
                f"preroll_bytes={stage.get('preroll_bytes')}"
            )
        if stage.get("stage") == "capture.summary":
            cap_bytes = int(stage.get("capture_bytes") or 0)
            cap_rms = float(stage.get("capture_rms_peak") or 0)
            print(
                f"\ncapture.summary: bytes={cap_bytes} "
                f"rms_peak={cap_rms} "
                f"inject={stage.get('inject_bytes_sent')}"
            )
            if cap_bytes == 0:
                print("  → gateway received ZERO capture bytes — Zoiper/Asterisk mic path dead")
            elif cap_rms < 120:
                print("  → capture flowing but very quiet — check Zoiper mic level / device")

    stt_texts = _stt_texts(rows, stages)
    if stt_texts:
        print("\n--- STT finals (order) ---")
        for i, text in enumerate(stt_texts, 1):
            print(f"  {i}. {text!r}")

    stt_requests = [s for s in stages if s.get("stage") == "stt.request"]
    stt_results = [s for s in stages if s.get("stage") == "stt.result"]
    if stt_requests or stt_results:
        print("\n--- STT chain (VAD segment → GigaAM) ---")
        for req in stt_requests:
            print(
                f"  request {req.get('utterance_id')}: "
                f"{req.get('duration_ms')}ms "
                f"rms={req.get('pcm_rms')} "
                f"bytes={req.get('pcm_bytes')} "
                f"slot={req.get('pending_slot')!r}"
            )
            if req.get("dump_path"):
                print(f"    dump: {req.get('dump_path')}")
        for res in stt_results:
            print(
                f"  result  {res.get('utterance_id')}: "
                f"raw={res.get('raw_text')!r} → text={res.get('text')!r} "
                f"quality={res.get('asr_quality')} "
                f"model={res.get('model_revision')!r} "
                f"stt_ms={res.get('stt_elapsed_ms')}"
            )
            if res.get("normalized_changed"):
                print("    → normalize changed raw output")
            rms_in = res.get("pcm_rms")
            if rms_in is not None and float(rms_in) < 280:
                print(f"    → quiet segment (rms={rms_in}) — STT may hallucinate")
    elif stt_texts:
        pass
    if echo_discarded:
        print(f"\nstt.echo_discarded events: {echo_discarded}")

    capture_pcm = ROOT / ".run" / "captures" / f"{call_id}.pcm"
    if capture_pcm.exists():
        print(f"\ncapture dump: {capture_pcm} ({capture_pcm.stat().st_size} bytes)")
    stt_dumps = sorted((ROOT / ".run" / "stt_dumps").glob(f"{call_id}_*.wav"))
    if stt_dumps:
        print("stt dumps:")
        for p in stt_dumps:
            print(f"  {p}")

    verdict = _verdict(
        cap_bytes=cap_bytes,
        cap_rms=cap_rms,
        listen_peaks=listen_peaks,
        stt_texts=stt_texts,
        echo_discarded=echo_discarded,
    )
    print(f"\n--- Verdict: {verdict} ---")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose call trace speak/hear path")
    parser.add_argument("call_id", help="e.g. sip-31365dee13")
    args = parser.parse_args(argv)
    return diagnose(args.call_id)


if __name__ == "__main__":
    raise SystemExit(main())
