#!/usr/bin/env python3
"""Forensic gate — per-turn echo/STT/interpret classification from live traces."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from packages.voice_runtime.forensic import classify_turn, normalize_speech_text, text_echo_similarity

ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = ROOT / ".run" / "traces"
DUMP_DIR = ROOT / ".run" / "stt_dumps"
MANIFEST_DEFAULT = Path(__file__).resolve().parent / "fixtures" / "stt_phone" / "manifest.jsonl"


@dataclass
class TurnForensic:
    call_id: str
    utterance_id: str
    bot_playout_end_ts: str = ""
    listen_open_ts: str = ""
    vad_speech_start_ts: str = ""
    vad_speech_end_ts: str = ""
    stt_audio_start_ts: str = ""
    stt_audio_end_ts: str = ""
    stt_rms: float = 0.0
    stt_duration_ms: int = 0
    stt_latency_ms: int = 0
    last_bot_text: str = ""
    stt_text: str = ""
    echo_similarity: float = 0.0
    echo_score_max: float = 0.0
    delivered_slot: str = ""
    interpret_path: str = ""
    interpret_latency_ms: int = 0
    dump_path: str = ""
    expected_text: str = ""
    verdict: str = ""
    notes: list[str] = field(default_factory=list)


def _load_manifest(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = f"{row.get('call_id')}:{row.get('utterance_id')}"
        expected = str(row.get("expected_text") or "").strip()
        if expected:
            out[key] = expected
    return out


def _stage_rows(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if row.get("type") == "stage.timing"
        and (row.get("payload") or {}).get("stage")
    ]


def _payload(row: dict) -> dict:
    return row.get("payload") or {}


def _last_bot_text_before(rows: list[dict], idx: int) -> str:
    for row in reversed(rows[:idx]):
        if row.get("type") != "renderer.phrase_ready":
            continue
        text = str(_payload(row).get("text") or "").strip()
        if text:
            return text
    return ""


def _parse_trace(path: Path, manifest: dict[str, str]) -> list[TurnForensic]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    call_id = path.stem
    turns: list[TurnForensic] = []
    last_bot_playout_end = ""
    last_listen_open = ""

    for idx, row in enumerate(rows):
        payload = _payload(row)
        stage = payload.get("stage")
        ts = str(row.get("ts") or "")

        if row.get("type") == "playback.completed":
            last_bot_playout_end = ts
        if stage == "listen.enabled":
            last_listen_open = ts
        if stage == "forensic.turn":
            uid = str(payload.get("utterance_id") or "")
            key = f"{call_id}:{uid}"
            turn = TurnForensic(
                call_id=call_id,
                utterance_id=uid,
                bot_playout_end_ts=str(payload.get("bot_playout_end_ts") or last_bot_playout_end),
                listen_open_ts=str(payload.get("listen_open_ts") or last_listen_open),
                vad_speech_start_ts=str(payload.get("vad_speech_start_ts") or ""),
                vad_speech_end_ts=str(payload.get("vad_speech_end_ts") or ""),
                stt_audio_start_ts=str(payload.get("stt_audio_start_ts") or ""),
                stt_audio_end_ts=str(payload.get("stt_audio_end_ts") or ""),
                stt_rms=float(payload.get("stt_rms") or 0),
                stt_duration_ms=int(payload.get("stt_duration_ms") or 0),
                stt_latency_ms=int(payload.get("stt_latency_ms") or 0),
                last_bot_text=str(payload.get("last_bot_text") or ""),
                stt_text=str(payload.get("stt_text") or ""),
                echo_similarity=float(payload.get("echo_similarity") or 0),
                echo_score_max=float(payload.get("echo_score_max") or 0),
                delivered_slot=str(payload.get("delivered_slot") or ""),
                interpret_path=str(payload.get("interpret_path") or ""),
                interpret_latency_ms=int(payload.get("interpret_latency_ms") or 0),
                dump_path=str(payload.get("dump_path") or ""),
                expected_text=manifest.get(key, ""),
            )
            turn.verdict = classify_turn(
                echo_similarity=turn.echo_similarity,
                echo_score_max=turn.echo_score_max,
                interpret_path=turn.interpret_path,
                interpret_latency_ms=turn.interpret_latency_ms,
                stt_text=turn.stt_text,
                expected_text=turn.expected_text or None,
            )
            turns.append(turn)
            continue

        if stage != "stt.request":
            continue

        uid = str(payload.get("utterance_id") or "")
        key = f"{call_id}:{uid}"
        turn = TurnForensic(
            call_id=call_id,
            utterance_id=uid,
            bot_playout_end_ts=last_bot_playout_end,
            listen_open_ts=last_listen_open,
            stt_audio_start_ts=ts,
            stt_rms=float(payload.get("pcm_rms") or 0),
            stt_duration_ms=int(payload.get("duration_ms") or 0),
            delivered_slot=str(payload.get("pending_slot") or ""),
            dump_path=str(payload.get("dump_path") or ""),
            expected_text=manifest.get(key, ""),
            last_bot_text=_last_bot_text_before(rows, idx),
        )

        for earlier in reversed(rows[:idx]):
            lp = _payload(earlier)
            lstage = lp.get("stage")
            lts = str(earlier.get("ts") or "")
            if lstage == "audio.speech_ended" and not turn.vad_speech_end_ts:
                turn.vad_speech_end_ts = lts
            if lstage == "audio.speech_started":
                turn.vad_speech_start_ts = lts
                break
            if lstage in {"stt.request", "forensic.turn"}:
                break

        for later in rows[idx + 1 :]:
            lp = _payload(later)
            lstage = lp.get("stage")
            lts = str(later.get("ts") or "")
            if lstage == "audio.speech_ended":
                pass
            if lstage == "stt.result" and lp.get("utterance_id") == uid:
                turn.stt_audio_end_ts = lts
                turn.stt_text = str(lp.get("text") or "")
                turn.stt_latency_ms = int(lp.get("stt_elapsed_ms") or 0)
                if not turn.stt_rms:
                    turn.stt_rms = float(lp.get("pcm_rms") or 0)
            if lstage == "interpret.fast_path" and lp.get("utterance_id") == uid:
                turn.interpret_path = "fast_contextual"
            if lstage == "stt.echo_discarded" and lp.get("utterance_id") == uid:
                turn.interpret_path = "echo_discarded"
            if lstage == "interpret.ready" and lp.get("utterance_id") == uid:
                turn.interpret_latency_ms = int(lp.get("elapsed_ms") or 0)
                if not turn.interpret_path:
                    # Heuristic: if no fast_path before interpret.ready → LLM/rules path.
                    turn.interpret_path = "llm"
                break

        if not turn.stt_text:
            for later in rows[idx + 1 :]:
                if later.get("type") == "stt.final" and _payload(later).get("utterance_id") == uid:
                    turn.stt_text = str(_payload(later).get("text") or turn.stt_text)
                    break

        if turn.last_bot_text and turn.stt_text:
            turn.echo_similarity = text_echo_similarity(turn.stt_text, turn.last_bot_text)

        echo_scores = []
        for later in rows[idx:]:
            lp = _payload(later)
            if lp.get("stage") == "audio.echo_classified":
                echo_scores.append(float(lp.get("score") or 0))
            if lp.get("stage") == "stt.request" and lp.get("utterance_id") != uid and echo_scores:
                break
            if lp.get("stage") == "stt.result" and lp.get("utterance_id") == uid:
                break
        if echo_scores:
            turn.echo_score_max = max(echo_scores)

        if not turn.dump_path:
            candidate = DUMP_DIR / f"{call_id}_{uid}.wav"
            if candidate.is_file():
                turn.dump_path = str(candidate)

        turn.verdict = classify_turn(
            echo_similarity=turn.echo_similarity,
            echo_score_max=turn.echo_score_max,
            interpret_path=turn.interpret_path,
            interpret_latency_ms=turn.interpret_latency_ms,
            stt_text=turn.stt_text,
            expected_text=turn.expected_text or None,
        )
        if turn.expected_text and turn.verdict == "STT_ERROR":
            turn.notes.append(
                f"expected={turn.expected_text!r} got={turn.stt_text!r}"
            )
        turns.append(turn)

    return turns


def _summarize_paths(turns: list[TurnForensic]) -> dict[str, int]:
    counts = Counter(t.interpret_path or "unknown" for t in turns)
    total = len(turns) or 1
    return {
        "turns": len(turns),
        "fast_contextual": counts.get("fast_contextual", 0),
        "fast_rules": counts.get("fast_rules", 0),
        "llm": counts.get("llm", 0),
        "echo_discarded": counts.get("echo_discarded", 0),
        "unknown": counts.get("unknown", 0),
        "fast_pct": round(
            100.0
            * (counts.get("fast_contextual", 0) + counts.get("fast_rules", 0))
            / total,
            1,
        ),
        "llm_pct": round(100.0 * counts.get("llm", 0) / total, 1),
    }


def analyze_call(call_id: str, *, manifest_path: Path) -> dict:
    trace = TRACE_DIR / f"{call_id}.jsonl"
    if not trace.is_file():
        raise FileNotFoundError(trace)
    manifest = _load_manifest(manifest_path)
    turns = _parse_trace(trace, manifest)
    verdicts = Counter(t.verdict for t in turns)
    return {
        "call_id": call_id,
        "trace": str(trace),
        "turns": [t.__dict__ for t in turns],
        "verdicts": dict(verdicts),
        "interpret_paths": _summarize_paths(turns),
    }


def _print_report(report: dict) -> None:
    print(f"Call: {report['call_id']}")
    print(f"Trace: {report['trace']}")
    print("\n--- Per-turn forensic ---")
    for turn in report["turns"]:
        print(
            f"\n{turn['utterance_id']} [{turn['verdict']}] "
            f"path={turn['interpret_path'] or '?'} "
            f"stt={turn['stt_latency_ms']}ms "
            f"interpret={turn['interpret_latency_ms']}ms "
            f"echo_sim={turn['echo_similarity']:.2f} "
            f"echo_max={turn['echo_score_max']:.2f}"
        )
        print(f"  bot: {turn['last_bot_text'][:80]!r}")
        print(f"  stt: {turn['stt_text']!r}")
        if turn.get("expected_text"):
            print(f"  expected: {turn['expected_text']!r}")
        if turn.get("dump_path"):
            print(f"  wav: {turn['dump_path']}")
        for note in turn.get("notes") or []:
            print(f"  note: {note}")
        if turn.get("bot_playout_end_ts"):
            print(f"  bot_playout_end: {turn['bot_playout_end_ts']}")
        if turn.get("listen_open_ts"):
            print(f"  listen_open: {turn['listen_open_ts']}")
        if turn.get("vad_speech_start_ts"):
            print(f"  vad: {turn['vad_speech_start_ts']} → {turn['vad_speech_end_ts']}")

    print("\n--- Verdict counts ---")
    for verdict, count in sorted(report["verdicts"].items()):
        print(f"  {verdict}: {count}")

    paths = report["interpret_paths"]
    print("\n--- Interpret paths ---")
    print(
        f"  fast={paths['fast_pct']}% "
        f"llm={paths['llm_pct']}% "
        f"(n={paths['turns']})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Forensic gate for live call traces")
    parser.add_argument("call_id", help="e.g. fs-68d06379")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_DEFAULT,
        help="JSONL with call_id, utterance_id, expected_text",
    )
    parser.add_argument("--json-out", type=Path, help="Write full report JSON")
    args = parser.parse_args(argv)

    report = analyze_call(args.call_id, manifest_path=args.manifest)
    _print_report(report)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nWrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
