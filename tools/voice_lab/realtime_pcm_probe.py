"""Offline PCM endpoint probe. Frame-time measurement, not live call latency.

No ASR, TTS, neural VAD, SIP or competitor execution. Runs the actual actor
and collector with EnergyVad on identical synthetic PCM before/after a patch.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks
from packages.voice_runtime.utterance_builder import UtteranceBuilder
from packages.voice_runtime.vad import EnergyVad, VadConfig


async def _noop(*args, **kwargs):
    return None


def _tone(hz: int) -> bytes:
    return b"".join(struct.pack("<h", int(4000 * math.sin(2 * math.pi * hz * i / 16000)))
                    for i in range(320))


async def probe(silence_ms: int, micro_pause_ms: int) -> dict:
    session = CallSession(call_id="pcm-probe", family_id="lab",
                          store=InMemoryCallRecordStore())
    actor = CallActor(
        call_id=session.state.call_id, family_id="lab", session=session,
        stt=SimpleNamespace(), tts=SimpleNamespace(cancel=_noop), llm=SimpleNamespace(),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
        config=CallActorConfig(lab_half_duplex=False, echo_ref_gate=False),
    )
    actor._vad = EnergyVad(16000, VadConfig(min_speech_ms=100, min_silence_ms=silence_ms))
    actor._utterance_builder = UtteranceBuilder(16000)
    actor._collector = actor._utterance_builder
    captured: list[bytes] = []

    async def capture(pcm, seq):
        captured.append(pcm)

    actor._handle_utterance = capture
    phrase = [_tone(200)] * 25 + [bytes(640)] * (micro_pause_ms // 20) + [_tone(250)] * 25
    input_frames = phrase + [bytes(640)] * 100
    submitted_after_ms = None
    for index, frame in enumerate(input_frames):
        await actor._process_uplink_vad_frame(frame, playback_active=False)
        await asyncio.sleep(0)
        if captured and submitted_after_ms is None:
            submitted_after_ms = (index + 1 - len(phrase)) * 20
    return {
        "vad": "EnergyVad", "vad_silence_ms": silence_ms, "micro_pause_ms": micro_pause_ms,
        "input_sha256": hashlib.sha256(b"".join(input_frames)).hexdigest(),
        "last_voiced_frame_to_submission_ms": submitted_after_ms,
        "utterances": len(captured),
        "post_onset_content_preserved": bool(captured and b"".join(phrase[5:]) in captured[0]),
    }


async def run() -> dict:
    sources = [
        "packages/voice_runtime/call_actor.py", "packages/voice_runtime/utterance_builder.py",
        "packages/voice_runtime/vad.py", "packages/voice_runtime/silero_vad.py",
        "services/stt/http_provider.py", "tools/voice_lab/latency_histogram.py",
    ]
    return {
        "layer": "synthetic_pcm", "time_basis": "20ms input frames, not wall-clock inference",
        "sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"])),
        "source_sha256": {s: hashlib.sha256(Path(s).read_bytes()).hexdigest() for s in sources},
        "live_sip": "NOT_RUN", "models": "NOT_RUN", "human_warmth": "NOT_RUN",
        "competitors": "NOT_RUN",
        "cases": [await probe(silence, pause) for silence in (500, 650)
                  for pause in (0, 100, 300, 500)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for case in result["cases"]:
        print(f"VAD={case['vad_silence_ms']}ms pause={case['micro_pause_ms']}ms "
              f"endpoint={case['last_voiced_frame_to_submission_ms']}ms "
              f"utterances={case['utterances']} content={case['post_onset_content_preserved']}")
    return 0 if all(c["utterances"] == 1 and c["post_onset_content_preserved"]
                    for c in result["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
