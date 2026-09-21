"""Offline stale-audio repro: recorded uplink WAV through the live VAD +
UtteranceBuilder chain. Reports per-segment index/bytes/sha256/timing.
A repeat of an earlier segment's sha256 == the stale-audio bug in the
segmentation chain (P0, before Stage B).

Usage:
  python3 tools/voice_lab/repro_stale_audio.py --call-id fs-338ee6ab
  python3 tools/voice_lab/repro_stale_audio.py --wav path/to/ws_raw_inbound.wav
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from packages.voice_runtime.silero_vad import create_vad
from packages.voice_runtime.utterance_builder import UtteranceBuilder


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--call-id", default=None)
    parser.add_argument("--wav", default=None)
    args = parser.parse_args()
    if args.wav:
        wav_path = Path(args.wav)
    elif args.call_id:
        wav_path = (
            ROOT / ".run" / "freeswitch-forensic" / args.call_id / "ws_raw_inbound.wav"
        )
    else:
        parser.error("pass --call-id or --wav")
        return
    w = wave.open(str(wav_path))
    raw = w.readframes(w.getnframes())
    sr = w.getframerate()
    frame_bytes = sr * 2 * 20 // 1000
    frames = [raw[i : i + frame_bytes] for i in range(0, len(raw), frame_bytes)]

    vad = create_vad(sr)
    builder = UtteranceBuilder(sr)
    segments: list[tuple[int, int, int, str, float, float]] = []
    offset = 0
    for index, frame in enumerate(frames):
        if len(frame) < frame_bytes:
            break
        started, ended = vad.feed(frame)
        active = bool(getattr(vad, "in_speech", False))
        built = builder.on_frame(
            frame, speech_started=started, speech_ended=ended, speech_active=active
        )
        if built is not None:
            pcm = built.pcm if hasattr(built, "pcm") else built
            start_s = (offset - len(pcm)) / 2 / sr
            end_s = offset / 2 / sr
            digest = hashlib.sha256(pcm).hexdigest()[:12]
            segments.append((len(segments), offset - len(pcm), len(pcm), digest, start_s, end_s))
        offset += len(frame)

    print(f"frames={len(frames)} segments={len(segments)}")
    seen: dict[str, int] = {}
    for seq, start, length, digest, t0, t1 in segments:
        mark = ""
        if digest in seen:
            mark = f" <-- REPEAT of segment {seen[digest]}"
        else:
            seen[digest] = seq
        print(
            f"seg#{seq} bytes[{start}:{start + length}] len={length}"
            f" t=[{t0:.1f}s-{t1:.1f}s] sha={digest}{mark}"
        )
    print(f"unique={len(seen)} total={len(segments)}")


if __name__ == "__main__":
    main()
