"""HTTP/SDK load probe; no SIP, VAD, admission or audible-call capacity claim.

Uses actual WAV metadata, STT output and validated canonical engine speech.
Only run against explicitly selected, isolated provider endpoints.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
import uuid
import wave
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue.validator import Validator
from services.stt.http_provider import HttpSTTProvider
from services.tts.http_provider import HttpTTSProvider


def load_pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError("probe requires mono PCM16 WAV")
        rate = audio.getframerate()
        pcm = audio.readframes(audio.getnframes())
    if not pcm:
        raise ValueError("empty WAV")
    return pcm, rate


def distribution(values: list[float]) -> dict:
    if not values:
        return {"samples": 0, "p50_ms": None, "p95_ms": None, "max_ms": None}
    ordered = sorted(values)
    return {"samples": len(values), "p50_ms": statistics.median(values),
            "p95_ms": ordered[math.ceil(len(values) * .95) - 1],
            "max_ms": ordered[-1]}


def _one_call(call_idx: int, wavs: list[Path], urls: dict[str, str],
              deadline_s: float = 20) -> dict:
    async def run():
        call_id = f"probe-{call_idx}-{uuid.uuid4().hex}"
        stt, tts = HttpSTTProvider(urls["stt"]), HttpTTSProvider(urls["tts"])
        session = CallSession(call_id=call_id, family_id="probe",
                              store=InMemoryCallRecordStore())
        if not session.uses_dialogue_engine():
            raise RuntimeError("enable IMVERA_DIALOGUE_ENGINE=1 explicitly")
        record = {"stt_calls": 0, "tts_calls": 0, "completed_turns": 0,
                  "errors": [], "turns": [], "opening": {}}
        stage = "opening"

        async def deliver(result, row):
            pending = [result]
            while pending:
                current = pending.pop(0)
                speech = [current.validated]
                for effect in current.followup_speak_effects:
                    speech.append(Validator.validate(
                        session._engine.effect_to_proposal(effect, session.turn_id)))
                for utterance in speech:
                    if not utterance.allowed:
                        raise RuntimeError("validator rejected probe speech")
                    if not utterance.speech:
                        continue
                    started = time.perf_counter()
                    pcm_bytes = 0
                    audio_seconds = 0.
                    first_pcm_ms = None
                    measurement = {"speech": utterance.speech, "intent": utterance.intent,
                                   "first_pcm_ms": None, "complete_ms": None,
                                   "audio_seconds": 0.}
                    row.setdefault("tts", []).append(measurement)
                    record["tts_calls"] += 1
                    async for chunk in tts.synthesize(
                        utterance.speech, call_id=call_id,
                        generation_id=utterance.generation_id,
                        phrase_id=uuid.uuid4().hex,
                        deadline=time.monotonic() + deadline_s,
                    ):
                        if chunk.pcm_s16le:
                            if first_pcm_ms is None:
                                first_pcm_ms = (time.perf_counter() - started) * 1000
                                measurement["first_pcm_ms"] = first_pcm_ms
                            pcm_bytes += len(chunk.pcm_s16le)
                            audio_seconds += len(chunk.pcm_s16le) / (2 * chunk.sample_rate)
                            measurement["audio_seconds"] = audio_seconds
                    if not pcm_bytes:
                        raise RuntimeError("TTS returned empty PCM")
                    measurement["complete_ms"] = (time.perf_counter() - started) * 1000
                    # Completed HTTP stream is simulated delivery, NOT phone hearing.
                    if not session.mark_spoken_action(utterance.generation_id):
                        raise RuntimeError("delivery acknowledgment failed")
                followup = session.pop_engine_playout_followup()
                if followup:
                    pending.append(followup)

        try:
            await deliver(session.start(), record["opening"])
            for index, path in enumerate(wavs):
                if session._engine.state.call_closed:
                    break
                row = {"fixture": str(path), "complete": False}
                record["turns"].append(row)
                stage = "stt"
                pcm, rate = load_pcm(path)
                started = time.perf_counter()
                record["stt_calls"] += 1
                recognized = await stt.transcribe_final(
                    pcm, rate, call_id=call_id, turn_id=index,
                    utterance_id=f"{call_id}-u{index}",
                    deadline=time.monotonic() + deadline_s,
                )
                row["stt_ms"] = (time.perf_counter() - started) * 1000
                row["recognized_text"] = recognized.text
                row["raw_text"] = recognized.raw_text
                row["asr_quality"] = recognized.asr_quality.value
                row["model_revision"] = recognized.model_revision
                stage = "engine"
                engine_started = time.perf_counter()
                result = session.handle_user_text(
                    recognized.text, asr_quality=recognized.asr_quality,
                    utterance_id=f"{call_id}-u{index}")
                row["engine_ms"] = (time.perf_counter() - engine_started) * 1000
                if not result.from_engine:
                    raise RuntimeError("unexpected non-engine turn")
                stage = "tts"
                await deliver(result, row)
                row["pipeline_complete_ms"] = (time.perf_counter() - started) * 1000
                first = next(iter(row.get("tts", [])), None)
                row["input_to_first_pcm_ms"] = (row["stt_ms"] + row["engine_ms"]
                                                + first["first_pcm_ms"] if first else None)
                row["complete"] = True
                record["completed_turns"] += 1
        except Exception as exc:
            # Exception type only: URLs/credentials may be present in error strings.
            record["errors"].append({"stage": stage, "type": type(exc).__name__})
        for row in record["turns"]:
            first = next(iter(row.get("tts", [])), None)
            if first and first["first_pcm_ms"] is not None:
                row["input_to_first_pcm_ms"] = (
                    row["stt_ms"] + row["engine_ms"] + first["first_pcm_ms"])
        return record
    return asyncio.run(run())


def summarize(results: list[dict]) -> dict:
    turns = [row for result in results for row in result["turns"]]
    return {
        "attempted_turns": len(turns),
        "completed_turns": sum(result["completed_turns"] for result in results),
        "stt_calls": sum(result["stt_calls"] for result in results),
        "tts_calls": sum(result["tts_calls"] for result in results),
        "errors_by_stage_type": dict(Counter(
            f'{error["stage"]}/{error["type"]}'
            for result in results for error in result["errors"])),
        "latency": {name: distribution([row[name] for row in turns
                                        if row.get(name) is not None])
                    for name in ("stt_ms", "engine_ms", "input_to_first_pcm_ms",
                                 "pipeline_complete_ms")},
        "calls": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--wav", type=Path, nargs="+", required=True,
                        help="ordered user WAVs; output may contain private speech")
    parser.add_argument("--stt", required=True)
    parser.add_argument("--tts", required=True)
    parser.add_argument("--deadline-s", type=float, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if any(level < 1 for level in args.levels) or not math.isfinite(args.deadline_s) \
            or args.deadline_s <= 0:
        parser.error("positive levels and finite positive deadline required")
    fixtures = []
    for path in args.wav:
        pcm, rate = load_pcm(path)
        fixtures.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "rate": rate, "duration_s": len(pcm) / (rate * 2)})
    report = {"boundary": "HTTP/SDK; simulated delivery; no SIP/VAD/admission",
              "source_sha": subprocess.check_output(
                  ["git", "-C", str(_ROOT), "rev-parse", "HEAD"], text=True).strip(),
              "source_dirty": bool(subprocess.check_output(
                  ["git", "-C", str(_ROOT), "status", "--porcelain"], text=True)),
              "fixtures": fixtures, "levels": {},
              "obs_mode": os.environ.get("IMVERA_OBS_MODE", "debug")}
    for level in args.levels:
        with ThreadPoolExecutor(max_workers=level) as pool:
            results = list(pool.map(lambda i: _one_call(i, args.wav,
                                {"stt": args.stt, "tts": args.tts}, args.deadline_s), range(level)))
        report["levels"][str(level)] = summarize(results)
        print(json.dumps({"level": level, **{k: v for k, v in report["levels"][str(level)].items()
                                            if k != "calls"}}), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
