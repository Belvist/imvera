#!/usr/bin/env python3
"""Synthetic Zoiper — full-stack HTTP call harness for MossVoice telephony.

Exercises the same path as FreeSWITCH Lua without a human SIP client:
  POST /calls → greeting
  POST /calls/{id}/turn_stream (real WAV, STT path) OR /turn_text (dialogue only)
  parse streaming frames + done.json semantics
  POST /calls/{id}/end

Usage:
    python3 scripts/synthetic_caller.py --strict
    python3 scripts/synthetic_caller.py --base http://127.0.0.1:9400 --json-report /tmp/syn_report.json
    python3 scripts/synthetic_caller.py --scenario bad_symptom_http
    python3 scripts/synthetic_caller.py --no-wav   # text-only (faster smoke)

Honest limits (see AUTO_TEST_REPORT.md):
    - Does NOT drive Zoiper GUI or real RTP; HTTP is primary.
    - FreeSWITCH loopback (--fs-loopback) is optional smoke only.
    - WAV STT quality depends on host STT (Qwen3-ASR / whisper).
    - macOS ``say`` + ffmpeg required for on-the-fly WAV generation.
"""
from __future__ import annotations

import argparse
import base64
import glob
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Literal, Optional, Sequence, Tuple

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TELEPHONY = os.path.join(_REPO, "telephony")
sys.path.insert(0, _TELEPHONY)

from conversation_system.reply.guards import (  # noqa: E402
    MINIMAL_FALLBACK,
    _ACTION_PROMISE_RE,
    looks_like_rescue_framing,
    reply_looks_broken,
)

TurnMode = Literal["text", "stream", "silent", "tone", "archive"]

AnchorRe = re.compile(r"хорошо\s+или\s+плохо", re.IGNORECASE)
ClarifyBareRe = re.compile(
    r"^(Услышала вас\.?|Услышала\.?|Повторите[,.]?\s*пожалуйста\.?)$",
    re.IGNORECASE,
)
GoodbyeRe = re.compile(
    r"(до\s+свидания|всего\s+доброго|берегите\s+себя|хорошего\s+(дня|вечера|отдыха)|"
    r"выздоравливайте|спокойной)",
    re.IGNORECASE,
)
RecordNotifyRe = re.compile(
    r"(записал|приложен|родн|близк|семь)",
    re.IGNORECASE,
)
SafetyRe = re.compile(
    r"(записала|близкие\s+увидят|перестраховал|тревожн|симптом|болит|упал)",
    re.IGNORECASE,
)

_WAV_CACHE: Dict[str, bytes] = {}
_ARCHIVE_WAVS: List[str] = []

# Short phrases are hard for STT — expand for TTS while keeping dialogue intent.
_TTS_PHRASE_EXPAND: Dict[str, str] = {
    "сильно": "болит очень сильно",
    "утром": "началось сегодня утром",
    "я упал": "я упал и не могу встать",
    "плохо": "мне плохо",
}


def _discover_archive_wavs() -> List[str]:
    global _ARCHIVE_WAVS
    if _ARCHIVE_WAVS:
        return _ARCHIVE_WAVS
    paths = sorted(glob.glob("/tmp/mossvoice/*/user-*.wav"))
    _ARCHIVE_WAVS = [p for p in paths if os.path.getsize(p) > 1000]
    return _ARCHIVE_WAVS


def _silent_wav(*, amplitude: int = 0, frames: int = 1600, rate: int = 8000) -> bytes:
    body = struct.pack(f"<{frames}h", *([amplitude] * frames))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(body)
    return buf.getvalue()


def _tone_wav(seconds: float = 1.0, freq: float = 440.0, rate: int = 8000) -> bytes:
    n = int(seconds * rate)
    samples = [int(8000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)]
    body = struct.pack(f"<{n}h", *samples)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(body)
    return buf.getvalue()


def _resample_wav_to_8k(data: bytes) -> bytes:
    if shutil.which("ffmpeg") is None:
        return data
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.wav")
        dst = os.path.join(td, "out.wav")
        with open(src, "wb") as f:
            f.write(data)
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-ar", "8000", "-ac", "1", dst],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 or not os.path.exists(dst):
            return data
        with open(dst, "rb") as f:
            return f.read()


def text_to_wav(text: str, *, rate: int = 8000) -> bytes:
    """Generate 8 kHz mono WAV via macOS say + ffmpeg (cached)."""
    if not text.strip():
        wav = _silent_wav(rate=rate)
        return wav
    spoken = _TTS_PHRASE_EXPAND.get(text.strip().lower(), text)
    key = f"{spoken}@{rate}"
    if key in _WAV_CACHE:
        return _WAV_CACHE[key]
    if shutil.which("say") is None:
        raise RuntimeError("macOS 'say' not found — cannot synthesize WAV for STT path")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found — cannot resample WAV for STT path")
    with tempfile.TemporaryDirectory() as td:
        aiff = os.path.join(td, "utt.aiff")
        mid = os.path.join(td, "utt16.wav")
        out = os.path.join(td, "utt8.wav")
        subprocess.run(
            ["say", "-v", "Milena", "-r", "140", "-o", aiff, spoken],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", aiff, "-ar", "16000", "-ac", "1", mid],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", mid, "-ar", str(rate), "-ac", "1", out],
            check=True,
            capture_output=True,
        )
        with open(out, "rb") as f:
            wav = f.read()
    _WAV_CACHE[key] = wav
    return wav


def archive_wav_for_text(text: str) -> bytes | None:
    """Best-effort: map phrase to archived user-*.wav by size heuristic."""
    archive = _discover_archive_wavs()
    if not archive:
        return None
    idx = abs(hash(text)) % len(archive)
    with open(archive[idx], "rb") as f:
        return _resample_wav_to_8k(f.read())


def wav_for_turn(text: str, mode: TurnMode) -> bytes:
    if mode == "silent":
        return _silent_wav()
    if mode == "tone":
        return _tone_wav()
    if mode == "archive":
        data = archive_wav_for_text(text)
        if data:
            return data
    return text_to_wav(text)


def parse_chunked_turn_stream(raw: bytes) -> Tuple[List[dict], str, str, bool]:
    """Parse HTTP chunked body with 4-byte length-prefixed JSON frames."""
    frames: List[dict] = []
    buf = raw
    while buf:
        if b"\r\n" in buf[:20]:
            line_end = buf.index(b"\r\n")
            try:
                chunk_len = int(buf[:line_end].split(b";")[0], 16)
            except ValueError:
                break
            buf = buf[line_end + 2:]
            if chunk_len == 0:
                break
            chunk = buf[:chunk_len]
            buf = buf[chunk_len + 2:]
            offset = 0
            while offset + 4 <= len(chunk):
                flen = int.from_bytes(chunk[offset:offset + 4], "big")
                offset += 4
                if offset + flen > len(chunk):
                    break
                payload = chunk[offset:offset + flen]
                offset += flen
                try:
                    frames.append(json.loads(payload.decode("utf-8")))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
        else:
            offset = 0
            while offset + 4 <= len(buf):
                flen = int.from_bytes(buf[offset:offset + 4], "big")
                offset += 4
                if flen <= 0 or offset + flen > len(buf):
                    break
                payload = buf[offset:offset + flen]
                offset += flen
                try:
                    frames.append(json.loads(payload.decode("utf-8")))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
            break

    transcript = ""
    reply = ""
    finished = False
    for fr in frames:
        if fr.get("transcript"):
            transcript = str(fr["transcript"])
        if fr.get("reply"):
            reply = str(fr["reply"])
        if fr.get("finished"):
            finished = bool(fr["finished"])
        if fr.get("done"):
            finished = finished or bool(fr.get("finished"))
    return frames, transcript, reply, finished


@dataclass
class TurnSpec:
    text: str = ""
    mode: TurnMode = "text"
    label: str = ""


@dataclass
class TurnResult:
    user: str
    reply: str
    transcript: Optional[str]
    finished: bool
    mode: TurnMode
    frames: int = 0


@dataclass
class ScenarioResult:
    name: str
    call_id: str
    passed: bool
    problems: List[str] = field(default_factory=list)
    turns: List[TurnResult] = field(default_factory=list)


class TelephonyClient:
    def __init__(self, base: str, timeout: float = 120.0) -> None:
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        *,
        content_type: str = "application/json",
    ) -> dict:
        headers = {"Content-Type": content_type} if body is not None else {}
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} {path}: {detail}") from exc
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def health(self) -> dict:
        return self._request("GET", "/health")

    def new_call(self, *, caller_id: str = "", mode: str = "check_in") -> Tuple[str, str]:
        payload: dict = {"mode": mode}
        if caller_id:
            payload["caller_id"] = caller_id
        body = self._request("POST", "/calls", json.dumps(payload).encode())
        if not body.get("ok", True) and not body.get("call_id"):
            raise RuntimeError(f"new_call failed: {body}")
        return str(body["call_id"]), str(body.get("greeting") or "")

    def turn_text(self, call_id: str, text: str) -> dict:
        return self._request(
            "POST",
            f"/calls/{call_id}/turn_text",
            json.dumps({"text": text}).encode(),
        )

    def turn_batch(self, call_id: str, wav: bytes) -> dict:
        payload = json.dumps({"audio_b64": base64.b64encode(wav).decode()}).encode()
        return self._request("POST", f"/calls/{call_id}/turn", payload)

    def turn_stream(self, call_id: str, wav: bytes) -> Tuple[List[dict], str, str, bool]:
        payload = json.dumps({"audio_b64": base64.b64encode(wav).decode()}).encode()
        req = urllib.request.Request(
            f"{self.base}/calls/{call_id}/turn_stream",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} turn_stream: {detail}") from exc
        return parse_chunked_turn_stream(raw)

    def end_call(self, call_id: str) -> dict:
        return self._request("POST", f"/calls/{call_id}/end", b"{}")


def _global_turn_checks(
    turn_idx: int,
    result: TurnResult,
    *,
    clarify_streak: int,
    total_turns: int,
) -> Tuple[List[str], int]:
    problems: List[str] = []
    reply = (result.reply or "").strip()
    if not reply:
        problems.append(f"  turn {turn_idx}: empty reply")
        return problems, clarify_streak

    if reply.count("?") > 1:
        problems.append(f"  turn {turn_idx}: double question: {reply!r}")

    if _ACTION_PROMISE_RE.search(reply) or looks_like_rescue_framing(reply):
        problems.append(f"  turn {turn_idx}: promise/rescue: {reply!r}")

    if reply_looks_broken(reply):
        problems.append(f"  turn {turn_idx}: broken reply: {reply!r}")

    is_clarify = (
        reply == MINIMAL_FALLBACK
        or ClarifyBareRe.match(reply)
        or (reply.rstrip(".") == "Услышала" and "?" not in reply)
        or "повторите" in reply.lower()
        or "слышите" in reply.lower()
    )
    if is_clarify:
        clarify_streak += 1
        if clarify_streak > 2:
            problems.append(f"  turn {turn_idx}: CLARIFY loop >2: {reply!r}")
    else:
        clarify_streak = 0

    mid_call = turn_idx < total_turns
    if mid_call and reply.rstrip(".") in (MINIMAL_FALLBACK.rstrip("."), "Услышала"):
        problems.append(f"  turn {turn_idx}: dead-end ack mid-call: {reply!r}")
    if mid_call and "?" not in reply and reply.lower().startswith("услышала"):
        problems.append(
            f"  turn {turn_idx}: bare heard-ack without question: {reply!r}"
        )

    return problems, clarify_streak


ScenarioCheck = Callable[[List[TurnResult]], List[str]]


def _scenario(
    name: str,
    turns: Sequence[TurnSpec],
    *checks: ScenarioCheck,
) -> Tuple[str, Sequence[TurnSpec], Tuple[ScenarioCheck, ...]]:
    return name, turns, checks


def _check_finished(turns: List[TurnResult]) -> List[str]:
    if not turns or not turns[-1].finished:
        return ["  expected finished=True on last turn"]
    if not any(GoodbyeRe.search(t.reply) for t in turns):
        return ["  expected goodbye phrase in closing reply"]
    return []


def _check_no_safety_alert(turns: List[TurnResult]) -> List[str]:
    joined = " ".join(t.reply for t in turns).lower()
    if "тревог" in joined and "перестраховал" in joined:
        return ["  unexpected safety alert on positive path"]
    return []


def _check_symptom_followup(turns: List[TurnResult]) -> List[str]:
    replies = " ".join(t.reply.lower() for t in turns)
    if not any(
        w in replies
        for w in ("голов", "бол", "симптом", "терпим", "беспокоит", "легче")
    ):
        return ["  expected symptom follow-up in replies"]
    return []


def _check_bad_symptom_no_dead_end(turns: List[TurnResult]) -> List[str]:
    for idx, tr in enumerate(turns, start=1):
        if tr.user in ("сильно", "утром") and ClarifyBareRe.match(tr.reply or ""):
            return [f"  turn {idx}: severity/time answer got dead-end: {tr.reply!r}"]
    return []


def _check_safety_path(turns: List[TurnResult]) -> List[str]:
    replies = " ".join(t.reply for t in turns)
    if not SafetyRe.search(replies):
        return ["  expected safety/record language after fall report"]
    return []


def _check_record_notify(turns: List[TurnResult]) -> List[str]:
    joined = " ".join(t.reply for t in turns)
    if not RecordNotifyRe.search(joined):
        return ["  expected record-notify phrase in conversation"]
    return []


def _check_first_silence_not_anchor(turns: List[TurnResult]) -> List[str]:
    if not turns:
        return ["  no turns recorded"]
    first = turns[0].reply
    if AnchorRe.search(first):
        return [f"  first silence turn should be ladder repeat, not anchor: {first!r}"]
    return []


def _check_repair(turns: List[TurnResult]) -> List[str]:
    if len(turns) < 2:
        return ["  need >=2 turns for repair"]
    second = turns[1].reply.lower()
    first_reply = turns[0].reply
    if "?" in turns[0].reply and second == first_reply.lower():
        return []
    if any(w in second for w in ("повтор", "сказал", "услышала", "?")):
        return []
    return ["  repair turn did not repeat or clarify prior reply"]


def _check_greeting_back(turns: List[TurnResult]) -> List[str]:
    if not turns:
        return ["  no turns"]
    first = turns[0].reply.lower()
    if "здравств" not in first and "добр" not in first:
        return [f"  expected greeting-back on 'здравствуйте': {turns[0].reply!r}"]
    return []


def _check_negated_fall_ok(turns: List[TurnResult]) -> List[str]:
    joined = " ".join(t.reply for t in turns).lower()
    if "упал" in joined and "записала" in joined and "перестраховал" in joined:
        return ["  negated fall should not trigger full safety alert"]
    return []


def _check_agenda_moves(turns: List[TurnResult]) -> List[str]:
    questions = [t.reply for t in turns if "?" in t.reply]
    if len(questions) < 2:
        return ["  expected multiple agenda questions across turns"]
    if len(set(questions)) < 2:
        return ["  agenda questions did not vary (possible stuck topic)"]
    return []


def _check_stt_uncertain_no_repeat(turns: List[TurnResult]) -> List[str]:
    for tr in turns:
        if "повторите" in (tr.reply or "").lower() and tr.user.startswith("Хорошее"):
            return [f"  stt_uncertain should not dead-end: {tr.reply!r}"]
    return []


def _check_time_of_day_closing(turns: List[TurnResult]) -> List[str]:
    last = turns[-1].reply.lower() if turns else ""
    if not any(w in last for w in ("дня", "вечера", "ночи", "отдыха", "выздоравливайте")):
        return [f"  expected time-of-day or band closing: {turns[-1].reply!r}"]
    return []


def _check_stream_had_transcript(turns: List[TurnResult]) -> List[str]:
    """STT path should produce transcript; soft-fail only when reply is clarify."""
    for tr in turns:
        if tr.mode not in ("stream", "archive") or not tr.user.strip():
            continue
        if (tr.transcript or "").strip():
            continue
        if ClarifyBareRe.match(tr.reply or "") or "повторите" in (tr.reply or "").lower():
            return [
                f"  STT path empty transcript + clarify for {tr.user!r}: {tr.reply!r}",
            ]
    return []


SCENARIOS: List[Tuple[str, Sequence[TurnSpec], Tuple[ScenarioCheck, ...]]] = [
    _scenario(
        "01_good_path_full",
        [
            TurnSpec("хорошо себя чувствую"),
            TurnSpec("настроение хорошее"),
            TurnSpec("спала нормально"),
            TurnSpec("пойду в магазин"),
            TurnSpec("да"),
        ],
        _check_agenda_moves,
        _check_no_safety_alert,
        _check_record_notify,
    ),
    _scenario(
        "02_bad_symptom_http",
        [
            TurnSpec("плохо"),
            TurnSpec("болит голова"),
            TurnSpec("сильно"),
            TurnSpec("утром"),
        ],
        _check_symptom_followup,
        _check_bad_symptom_no_dead_end,
    ),
    _scenario(
        "03_critical_fall",
        [TurnSpec("я упал и не могу встать")],
        _check_safety_path,
        _check_record_notify,
    ),
    _scenario(
        "04_silence_ladder",
        [
            TurnSpec("", mode="silent"),
            TurnSpec("", mode="silent"),
            TurnSpec("", mode="silent"),
            TurnSpec("хорошо"),
        ],
        _check_first_silence_not_anchor,
    ),
    _scenario(
        "05_goodbye_mid_call",
        [TurnSpec("всё хорошо"), TurnSpec("до свидания")],
        _check_finished,
    ),
    _scenario(
        "06_refusal_wrap",
        [TurnSpec("всё нормально"), TurnSpec("нет, спасибо")],
        _check_finished,
    ),
    _scenario(
        "07_repair_repeat",
        [TurnSpec("хорошо"), TurnSpec("повторите пожалуйста")],
        _check_repair,
    ),
    _scenario(
        "08_hello_back",
        [TurnSpec("здравствуйте"), TurnSpec("хорошо")],
        _check_greeting_back,
    ),
    _scenario(
        "09_side_question",
        [TurnSpec("какое сегодня число?"), TurnSpec("спасибо"), TurnSpec("хорошо")],
    ),
    _scenario(
        "10_negated_fall",
        [TurnSpec("я не упал"), TurnSpec("всё хорошо")],
        _check_negated_fall_ok,
    ),
    _scenario(
        "11_positive_no_false_red",
        [
            TurnSpec("отлично, ничего не болело"),
            TurnSpec("настроение хорошее"),
        ],
        _check_no_safety_alert,
    ),
    _scenario(
        "12_safety_confirm_chain",
        [
            TurnSpec("голова сильно болит"),
            TurnSpec("да"),
            TurnSpec("стало легче"),
        ],
        _check_symptom_followup,
    ),
    _scenario(
        "13_stt_uncertain_mood",
        [
            TurnSpec("Привет, хорошо себя чувствую."),
            TurnSpec("Хорошее настроение."),
            TurnSpec("Хорошо."),
            TurnSpec("да"),
            TurnSpec("да"),
        ],
        _check_stt_uncertain_no_repeat,
        _check_agenda_moves,
    ),
    _scenario(
        "14_medium_wellness",
        [
            TurnSpec("ну так себе"),
            TurnSpec("устала немного"),
            TurnSpec("спала прерывисто"),
        ],
        _check_agenda_moves,
    ),
    _scenario(
        "15_closing_direct_poka",
        [TurnSpec("хорошо"), TurnSpec("давайте, пока")],
        _check_finished,
    ),
    _scenario(
        "16_symptom_improvement",
        [
            TurnSpec("голова болит"),
            TurnSpec("стало легче"),
            TurnSpec("да"),
        ],
    ),
    _scenario(
        "17_short_da_wellness",
        [TurnSpec("нормально"), TurnSpec("да"), TurnSpec("да")],
    ),
    _scenario(
        "18_narrative_story",
        [
            TurnSpec(
                "Внучка приезжала, мы чай пили на кухне и долго разговаривали"
            ),
            TurnSpec("да"),
        ],
    ),
    _scenario(
        "19_help_request",
        [TurnSpec("мне нужна помощь")],
    ),
    _scenario(
        "20_wellness_good_short",
        [TurnSpec("всё хорошо"), TurnSpec("нормально"), TurnSpec("выспался")],
    ),
    _scenario(
        "21_echo_then_speech",
        [TurnSpec("", mode="silent", label="<echo-skip>"), TurnSpec("всё хорошо")],
    ),
    _scenario(
        "22_low_conf_recovery",
        [TurnSpec("", mode="silent"), TurnSpec("хорошо")],
    ),
    _scenario(
        "23_good_path_wav_stream",
        [
            TurnSpec("хорошо себя чувствую", mode="stream"),
            TurnSpec("настроение отличное", mode="stream"),
            TurnSpec("спала хорошо", mode="stream"),
        ],
        _check_stream_had_transcript,
        _check_agenda_moves,
    ),
    _scenario(
        "24_bad_symptom_wav_stream",
        [
            TurnSpec("плохо", mode="stream"),
            TurnSpec("болит голова", mode="stream"),
            TurnSpec("сильно", mode="stream"),
        ],
        _check_bad_symptom_no_dead_end,
        _check_stream_had_transcript,
    ),
    _scenario(
        "25_greeting_back_wav",
        [
            TurnSpec("здравствуйте", mode="stream"),
            TurnSpec("хорошо", mode="stream"),
        ],
        _check_greeting_back,
        _check_stream_had_transcript,
    ),
    _scenario(
        "26_critical_fall_wav",
        [TurnSpec("я упал", mode="stream")],
        _check_safety_path,
        _check_stream_had_transcript,
    ),
    _scenario(
        "27_silence_wav_stream",
        [
            TurnSpec("", mode="silent"),
            TurnSpec("хорошо", mode="stream"),
        ],
        _check_first_silence_not_anchor,
    ),
    _scenario(
        "28_archive_wav_turn",
        [
            TurnSpec("хорошо", mode="stream"),
            TurnSpec("нормально", mode="stream"),
        ],
        _check_stream_had_transcript,
    ),
    _scenario(
        "29_goodbye_wav",
        [
            TurnSpec("всё хорошо", mode="stream"),
            TurnSpec("до свидания", mode="stream"),
        ],
        _check_finished,
    ),
    _scenario(
        "30_time_closing_good",
        [
            TurnSpec("отлично"),
            TurnSpec("хорошо"),
            TurnSpec("да"),
        ],
        _check_time_of_day_closing,
    ),
]


def _resolve_mode(spec: TurnSpec, *, allow_wav: bool) -> TurnMode:
    if spec.mode == "text":
        return "text"
    if not allow_wav:
        return "text"
    return spec.mode


def _run_turns(
    client: TelephonyClient,
    call_id: str,
    specs: Sequence[TurnSpec],
    *,
    allow_wav: bool,
) -> Tuple[List[TurnResult], List[str]]:
    results: List[TurnResult] = []
    problems: List[str] = []
    clarify_streak = 0

    for idx, spec in enumerate(specs, start=1):
        mode = _resolve_mode(spec, allow_wav=allow_wav)
        user_label = spec.label or spec.text or f"<{mode}>"

        try:
            if mode == "text":
                body = client.turn_text(call_id, spec.text)
                reply = str(body.get("reply") or "").strip()
                finished = bool(body.get("finished"))
                transcript = spec.text
                frame_count = 0
            else:
                wav = wav_for_turn(spec.text, mode)
                frames, transcript, reply, finished = client.turn_stream(call_id, wav)
                frame_count = len(frames)
                if not reply and frames:
                    for fr in reversed(frames):
                        if fr.get("reply"):
                            reply = str(fr["reply"])
                            break
        except RuntimeError as exc:
            problems.append(f"  turn {idx}: {exc}")
            continue

        tr = TurnResult(
            user=user_label,
            reply=reply,
            transcript=transcript if isinstance(transcript, str) else None,
            finished=finished,
            mode=mode,
            frames=frame_count,
        )
        results.append(tr)

        turn_problems, clarify_streak = _global_turn_checks(
            idx, tr, clarify_streak=clarify_streak, total_turns=len(specs)
        )
        problems.extend(turn_problems)

        if finished and idx < len(specs):
            problems.append(f"  turn {idx}: call finished early (expected more turns)")
            break

    return results, problems


def run_scenario(
    client: TelephonyClient,
    name: str,
    turns: Sequence[TurnSpec],
    checks: Sequence[ScenarioCheck],
    *,
    allow_wav: bool,
) -> ScenarioResult:
    call_id, greeting = client.new_call()
    problems: List[str] = []
    if not greeting:
        problems.append("  missing greeting on new_call")
    if "чувствуете" not in greeting.lower() and "поживаете" not in greeting.lower():
        problems.append(f"  greeting missing wellness question: {greeting!r}")

    turn_results, turn_problems = _run_turns(
        client, call_id, turns, allow_wav=allow_wav,
    )
    problems.extend(turn_problems)

    for check in checks:
        problems.extend(check(turn_results))

    try:
        client.end_call(call_id)
    except RuntimeError as exc:
        problems.append(f"  end_call: {exc}")

    return ScenarioResult(
        name=name,
        call_id=call_id,
        passed=len(problems) == 0,
        problems=problems,
        turns=turn_results,
    )


def _print_result(res: ScenarioResult) -> None:
    status = "PASS" if res.passed else "FAIL"
    print(f"{status}  {res.name}  call_id={res.call_id}")
    for tr in res.turns:
        user = tr.user[:60] + ("…" if len(tr.user) > 60 else "")
        reply = tr.reply[:100] + ("…" if len(tr.reply) > 100 else "")
        stt = ""
        if tr.mode != "text" and tr.transcript:
            stt = f" [stt={tr.transcript[:40]!r}]"
        print(f"    U: {user}{stt}")
        print(f"    V: {reply}")
    for p in res.problems:
        print(p)


def _optional_fs_loopback() -> Tuple[bool, str]:
    fs_cli = shutil.which("fs_cli")
    if not fs_cli:
        return False, "fs_cli not found"
    cmd = [fs_cli, "-x", "originate loopback/4400/default 4400 XML default"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, out.strip() or f"exit {proc.returncode}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=os.environ.get("MOSS_TELEPHONY_URL", "http://127.0.0.1:9400"),
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-wav", action="store_true", help="Use turn_text only (skip STT path)")
    parser.add_argument("--scenario", default="", help="Run single scenario by name")
    parser.add_argument("--fs-loopback", action="store_true")
    parser.add_argument("--json-report", default="", help="Write JSON summary to path")
    parser.add_argument("--iteration", type=int, default=1, help="Iteration label for reports")
    args = parser.parse_args(argv)

    client = TelephonyClient(args.base)
    try:
        health = client.health()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: telephony not reachable at {args.base}: {exc}")
        print("Hint: make up telephony")
        return 2

    if not health.get("ok"):
        print(f"ERROR: telephony unhealthy: {health}")
        return 2

    allow_wav = not args.no_wav
    if allow_wav and shutil.which("say") is None:
        print("WARN: macOS 'say' missing — STT scenarios will use turn_text fallback")
        allow_wav = False

    print(
        f"Telephony OK @ {args.base}  iteration={args.iteration}  "
        f"wav={'on' if allow_wav else 'off'}  archive={len(_discover_archive_wavs())} files"
    )

    selected = SCENARIOS
    if args.scenario:
        selected = [s for s in SCENARIOS if s[0] == args.scenario]
        if not selected:
            print(f"ERROR: unknown scenario {args.scenario!r}")
            return 2

    results: List[ScenarioResult] = []
    for name, turns, checks in selected:
        try:
            res = run_scenario(
                client, name, turns, checks, allow_wav=allow_wav,
            )
        except Exception as exc:  # noqa: BLE001
            res = ScenarioResult(
                name=name,
                call_id="?",
                passed=False,
                problems=[f"  exception: {exc}"],
            )
        results.append(res)
        _print_result(res)
        print()

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    wav_modes = sum(
        1 for _, turns, _ in selected
        for t in turns
        if t.mode in ("stream", "silent", "tone", "archive")
    )
    print(f"=== SYNTHETIC CALLER iteration {args.iteration}: {passed}/{total} PASS ===")
    print(f"    wav/stream turn specs: {wav_modes} (allow_wav={allow_wav})")

    report = {
        "iteration": args.iteration,
        "passed": passed,
        "total": total,
        "base": args.base,
        "allow_wav": allow_wav,
        "scenarios": [
            {
                "name": r.name,
                "call_id": r.call_id,
                "passed": r.passed,
                "problems": r.problems,
            }
            for r in results
        ],
    }
    if args.json_report:
        with open(args.json_report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    if args.fs_loopback:
        ok, msg = _optional_fs_loopback()
        print(f"FS loopback originate: {'OK' if ok else 'SKIP/FAIL'} — {msg}")

    print(
        "\nLimits: no Zoiper RTP; HTTP turn_stream simulates Lua audio upload; "
        "loopback FS is echo-prone smoke only."
    )

    if args.strict and passed < total:
        failed = [r.name for r in results if not r.passed]
        print(f"FAILED: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
