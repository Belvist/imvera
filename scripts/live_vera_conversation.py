#!/usr/bin/env python3
"""Live Vera conversation tester — real FreeSWITCH → Lua → telephony path.

Unlike synthetic_caller.py (HTTP turn_stream/turn_text), this harness:
  1. Originates a call via ESL/fs_cli to loopback/4400 (same dialplan as Zoiper).
  2. Injects caller speech with uuid_broadcast on the answered B-leg (aleg).
  3. Captures Vera replies from /tmp/mossvoice/<call_id>/reply-*.wav.
  4. Transcribes replies via the host STT service (default :9705).
  5. Evaluates turn-by-turn dialogue quality (dead-ends, repeats, safety).

Requirements:
  - FreeSWITCH running with 4400 → moss_agent.lua
  - telephony healthy @ MOSS_TELEPHONY_URL (default http://127.0.0.1:9400)
  - MOSS_ESL_PASSWORD or ~/.fs_cli_conf
  - macOS ``say`` + ``ffmpeg`` for user phrase WAVs
  - Host STT @ MOSS_STT_HOST (default http://127.0.0.1:9705)

Usage:
    python3 scripts/live_vera_conversation.py
    python3 scripts/live_vera_conversation.py --scenario good_path --strict
    python3 scripts/live_vera_conversation.py --originate bridge
    python3 scripts/live_vera_conversation.py --report /tmp/live_vera_report.json

Honest limits:
  - Loopback B-leg has no real RTP; uuid_broadcast injects media directly.
  - Timing vs Lua ``record`` is heuristic (post-greeting window).
  - Not a substitute for a live Zoiper call with a real microphone.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence, Tuple

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VR = os.path.join(_REPO, "voice_runtime")
_TELEPHONY = os.path.join(_REPO, "telephony")
for _p in (_VR, _TELEPHONY):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from esl_client import EslClient, ESLProtocolError  # noqa: E402
from conversation_system.reply.guards import (  # noqa: E402
    MINIMAL_FALLBACK,
    _ACTION_PROMISE_RE,
    looks_like_rescue_framing,
    reply_looks_broken,
)

OriginateMode = Literal["loopback", "bridge"]

MOSSVOICE_DIR = os.environ.get("MOSS_OUTDIR", "/tmp/mossvoice")
TELEPHONY_URL = os.environ.get("MOSS_TELEPHONY_URL", "http://127.0.0.1:9400")
STT_URL = os.environ.get("MOSS_STT_HOST", "http://127.0.0.1:9705").rstrip("/")

ClarifyRe = re.compile(
    r"(повторите|не\s+расслыш|слышите|алло)",
    re.IGNORECASE,
)
GoodbyeRe = re.compile(
    r"(до\s+свидания|всего\s+доброго|берегите\s+себя|хорошего\s+(дня|вечера))",
    re.IGNORECASE,
)
SafetyRe = re.compile(
    r"(записал[ао]?|близк|родн|семь|приложен|перестраховал|тревожн|упал|болит|оставайтесь)",
    re.IGNORECASE,
)

_TTS_EXPAND: Dict[str, str] = {
    "сильно": "болит очень сильно",
    "утром": "началось сегодня утром",
    "плохо": "мне плохо",
    "да": "да, хорошо",
}


def _read_esl_password() -> str:
    pw = os.environ.get("MOSS_ESL_PASSWORD", "").strip()
    if pw:
        return pw
    conf = os.path.expanduser("~/.fs_cli_conf")
    if not os.path.isfile(conf):
        raise RuntimeError(
            "MOSS_ESL_PASSWORD not set and ~/.fs_cli_conf missing"
        )
    text = open(conf, encoding="utf-8", errors="replace").read()
    m = re.search(r"^password\s*=>\s*(\S+)", text, re.M)
    if not m:
        raise RuntimeError(f"no password in {conf}")
    return m.group(1)


def _wav_duration_sec(path: str) -> float:
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except wave.Error:
        return 1.0


def text_to_wav(text: str, *, rate: int = 8000) -> str:
    """Synthesize 8 kHz mono WAV; returns path in a temp dir (caller owns dir)."""
    spoken = _TTS_EXPAND.get(text.strip().lower(), text)
    if not spoken.strip():
        td = tempfile.mkdtemp(prefix="live_vera_silence_")
        path = os.path.join(td, "silence.wav")
        frames = 1600
        body = struct.pack(f"<{frames}h", *([0] * frames))
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(body)
        return path
    if shutil.which("say") is None or shutil.which("ffmpeg") is None:
        raise RuntimeError("macOS say + ffmpeg required for speech synthesis")
    td = tempfile.mkdtemp(prefix="live_vera_utt_")
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
    return out


def transcribe_wav(path: str, *, timeout: float = 60.0) -> Tuple[str, float]:
    """POST multipart to host STT; returns (text, confidence)."""
    boundary = f"----mossboundary{int(time.time() * 1000)}"
    with open(path, "rb") as f:
        audio = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="reply.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + audio + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{STT_URL}/transcribe",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"STT HTTP {exc.code}: {detail}") from exc
    text = str(data.get("text") or data.get("transcript") or "").strip()
    conf = float(data.get("confidence", data.get("conf", 1.0)) or 1.0)
    return text, conf


def telephony_end_call(call_id: str) -> None:
    req = urllib.request.Request(
        f"{TELEPHONY_URL.rstrip('/')}/calls/{call_id}/end",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def telephony_get_calls() -> List[dict]:
    req = urllib.request.Request(f"{TELEPHONY_URL.rstrip('/')}/calls")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode())
    return list(body.get("calls") or [])


def telephony_cleanup_stale_calls() -> int:
    """End orphaned calls blocking admission (capacity limit)."""
    ended = 0
    for c in telephony_get_calls():
        cid = str(c.get("call_id") or "")
        if cid and not c.get("finished"):
            telephony_end_call(cid)
            ended += 1
    return ended


def telephony_health() -> dict:
    with urllib.request.urlopen(
        f"{TELEPHONY_URL.rstrip('/')}/health", timeout=10,
    ) as resp:
        return json.loads(resp.read().decode())


def fs_status() -> str:
    fs_cli = shutil.which("fs_cli")
    if not fs_cli:
        return "fs_cli not found"
    proc = subprocess.run(
        [fs_cli, "-x", "status"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return (proc.stdout or proc.stderr or "").strip()


def stt_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{STT_URL}/ready", timeout=5) as resp:
            data = json.loads(resp.read().decode())
        return bool(data.get("ready"))
    except Exception:
        return False


@dataclass
class TurnSpec:
    text: str
    label: str = ""


@dataclass
class LiveTurn:
    user_text: str
    user_wav: str
    reply_wav: str
    reply_text: str
    stt_confidence: float
    user_wav_size: int = 0
    problems: List[str] = field(default_factory=list)


@dataclass
class ScenarioResult:
    name: str
    call_id: str
    channel_uuid: str
    passed: bool
    turns: List[LiveTurn] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    path_notes: str = ""


SCENARIOS: Dict[str, List[TurnSpec]] = {
    "good_path": [
        TurnSpec("хорошо себя чувствую"),
        TurnSpec("настроение хорошее"),
        TurnSpec("спала нормально"),
        TurnSpec("пойду в магазин"),
    ],
    "bad_symptom": [
        TurnSpec("плохо"),
        TurnSpec("болит голова"),
        TurnSpec("сильно"),
    ],
    "greeting_back": [
        TurnSpec("здравствуйте"),
        TurnSpec("хорошо"),
        TurnSpec("нормально"),
    ],
    "critical_fall": [
        TurnSpec("я упал и не могу встать"),
    ],
    "goodbye": [
        TurnSpec("всё хорошо"),
        TurnSpec("до свидания"),
    ],
}


class ReplyWatcher:
    """Watch /tmp/mossvoice/<call_id>/reply-*.wav for new files."""

    def __init__(self, call_id: str) -> None:
        self.call_dir = os.path.join(MOSSVOICE_DIR, call_id)
        self._seen = set(self._list())

    def _list(self) -> List[str]:
        if not os.path.isdir(self.call_dir):
            return []
        return sorted(glob.glob(os.path.join(self.call_dir, "reply-*.wav")))

    def wait_for_new(
        self,
        *,
        timeout: float = 45.0,
        min_size: int = 8000,
    ) -> Optional[str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for path in self._list():
                if path in self._seen:
                    continue
                try:
                    if os.path.getsize(path) >= min_size:
                        self._seen.add(path)
                        return path
                except OSError:
                    continue
            time.sleep(0.25)
        return None

    def count(self) -> int:
        return len(self._list())


def cleanup_loopback_channels(esl: EslClient) -> int:
    """Hang up stale loopback/4400 test legs only (not unrelated calls)."""
    raw = esl.api("show channels as json", timeout=15)
    if "{" not in raw:
        return 0
    rows = json.loads(raw[raw.index("{"):]).get("rows", [])
    killed = 0
    for row in rows:
        name = str(row.get("name") or "")
        dest = str(row.get("dest") or row.get("destination_number") or "")
        if "loopback/4400" in name or (
            dest == "4400" and "loopback" in name.lower()
        ):
            uid = row.get("uuid") or row.get("call_uuid")
            if uid:
                esl.api(f"uuid_kill {uid}")
                killed += 1
    return killed


class LiveFsConversation:
    def __init__(
        self,
        *,
        extension: str = "4400",
        originate_mode: OriginateMode = "loopback",
        greeting_wait: float = 14.0,
        post_reply_wait: float = 6.0,
        post_broadcast_pad: float = 1.0,
    ) -> None:
        self.extension = extension
        self.originate_mode = originate_mode
        self.greeting_wait = greeting_wait
        self.post_reply_wait = post_reply_wait
        self.post_broadcast_pad = post_broadcast_pad
        self._esl: Optional[EslClient] = None
        self._a_uuid: str = ""
        self._b_uuid: str = ""
        self._temp_dirs: List[str] = []
        self._inject_dir = os.path.join(MOSSVOICE_DIR, "live_inject")
        os.makedirs(self._inject_dir, mode=0o700, exist_ok=True)

    def close(self) -> None:
        if self._esl:
            for uid in (self._a_uuid, self._b_uuid):
                if uid:
                    try:
                        self._esl.api(f"uuid_kill {uid}")
                    except (ESLProtocolError, OSError):
                        pass
            try:
                self._esl.close()
            except OSError:
                pass
            self._esl = None
        for td in self._temp_dirs:
            shutil.rmtree(td, ignore_errors=True)
        self._temp_dirs.clear()

    def _snapshot_call_ids(self) -> set[str]:
        try:
            return {c.get("call_id", "") for c in telephony_get_calls()}
        except Exception:
            return set()

    def _wait_new_call_id(self, before: set[str], timeout: float = 30.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                for c in telephony_get_calls():
                    cid = str(c.get("call_id") or "")
                    if cid and cid not in before:
                        return cid
            except Exception:
                pass
            time.sleep(0.3)
        raise RuntimeError("timeout waiting for telephony call_id after originate")

    def _wait_event(
        self,
        *,
        event_name: str,
        uuid: str = "",
        timeout: float = 20.0,
    ) -> Optional[dict]:
        assert self._esl is not None
        deadline = time.time() + timeout
        while time.time() < deadline:
            ev = self._esl.next_event(timeout=0.5)
            if not ev:
                continue
            if ev.get("Event-Name") != event_name:
                continue
            ev_uid = ev.get("Unique-ID") or ev.get("Channel-Call-UUID") or ""
            if uuid and ev_uid and ev_uid != uuid:
                continue
            return ev
        return None

    def _find_b_leg(self, a_uuid: str) -> str:
        """Prefer inbound loopback/<ext>-b leg running Lua/record/playback."""
        assert self._esl is not None
        ext = self.extension
        raw = self._esl.api("show channels as json", timeout=15)
        if "{" not in raw:
            return ""
        rows = json.loads(raw[raw.index("{"):]).get("rows", [])
        candidates: List[Tuple[int, str]] = []
        for row in rows:
            uid = row.get("uuid") or row.get("call_uuid") or ""
            if not uid or uid == a_uuid:
                continue
            name = str(row.get("name") or "")
            dest = str(row.get("dest") or row.get("destination_number") or "")
            direction = str(row.get("direction") or "").lower()
            app = str(row.get("application") or "").lower()
            score = 0
            if f"loopback/{ext}-b" in name:
                score += 10
            if direction == "inbound":
                score += 5
            if dest == ext:
                score += 3
            if app in ("lua", "record", "playback", "park"):
                score += 2
            if score > 0:
                candidates.append((score, uid))
        if not candidates:
            return ""
        candidates.sort(reverse=True)
        return candidates[0][1]

    def originate(self) -> Tuple[str, str]:
        """Return (call_id, b_uuid). Raises on failure."""
        pwd = _read_esl_password()
        self._esl = EslClient(password=pwd)
        stale = cleanup_loopback_channels(self._esl)
        if stale:
            print(f"  cleaned {stale} stale loopback channel(s)")
            time.sleep(0.5)
        before = self._snapshot_call_ids()
        a_uuid = self._esl.api("create_uuid").strip()
        self._a_uuid = a_uuid
        ext = self.extension

        if self.originate_mode == "bridge":
            cmd = (
                f"originate {{origination_caller_id_number=1000,"
                f"default_password=override,origination_uuid={a_uuid}}}"
                f"user/1000 &bridge(loopback/{ext}/default)"
            )
        else:
            hold = "silence_stream://600000"
            cmd = (
                f"originate {{origination_caller_id_number=1000,"
                f"default_password=override,origination_uuid={a_uuid}}}"
                f"loopback/{ext}/default &playback({hold})"
            )
        reply = self._esl.api(cmd, timeout=30)
        if "-ERR" in (reply or ""):
            raise RuntimeError(f"originate failed: {reply}")

        b_uuid = ""
        deadline = time.time() + 25
        while time.time() < deadline and not b_uuid:
            ev = self._esl.next_event(timeout=0.4)
            if ev and ev.get("Event-Name") == "CHANNEL_ANSWER":
                uid = ev.get("Unique-ID") or ""
                dest = str(ev.get("Caller-Destination-Number") or "")
                name = str(ev.get("Channel-Name") or "")
                if uid != a_uuid and (
                    dest == ext or f"{ext}-b" in name
                ):
                    b_uuid = uid
                    break
            if not b_uuid:
                b_uuid = self._find_b_leg(a_uuid)
        if not b_uuid:
            raise RuntimeError(
                f"B-leg on {ext} not found after originate (A={a_uuid[:8]})"
            )
        self._b_uuid = b_uuid
        call_id = self._wait_new_call_id(before)
        return call_id, b_uuid

    def _prepare_inject_wav(self, wav_path: str, turn_idx: int) -> str:
        """Copy into shared /tmp/mossvoice so FreeSWITCH can read the file."""
        base = os.path.basename(wav_path)
        dest = os.path.join(self._inject_dir, f"t{turn_idx}_{base}")
        shutil.copy2(wav_path, dest)
        os.chmod(dest, 0o600)
        return dest

    def inject_speech(self, wav_path: str, *, turn_idx: int) -> None:
        """Inject caller audio on loopback A-leg (verified on VoiceRuntime 4400)."""
        assert self._esl is not None and self._a_uuid
        inject_path = self._prepare_inject_wav(wav_path, turn_idx)
        if not os.path.isfile(inject_path):
            raise FileNotFoundError(inject_path)
        if turn_idx == 1:
            time.sleep(self.greeting_wait)
        else:
            time.sleep(self.post_reply_wait)
        self._esl.api(
            f"uuid_broadcast {self._a_uuid} playback::{inject_path} aleg",
            timeout=30,
        )
        time.sleep(_wav_duration_sec(inject_path) + self.post_broadcast_pad)

    def run_scenario(self, name: str, specs: Sequence[TurnSpec]) -> ScenarioResult:
        problems: List[str] = []
        turns: List[LiveTurn] = []
        call_id = ""
        b_uuid = ""
        path_notes = (
            f"ext={self.extension}; originate=loopback/{self.extension}; "
            f"inject=A-leg uuid_broadcast; "
            f"dialplan={'VoiceRuntime park' if self.extension == '4400' else 'Lua moss_agent'}; "
            f"capture={MOSSVOICE_DIR}/<call_id>/reply-*.wav + STT"
        )
        try:
            call_id, b_uuid = self.originate()
            watcher = ReplyWatcher(call_id)
            route = "VoiceRuntime" if self.extension == "4400" else "Lua"
            print(
                f"  call_id={call_id}  a_leg={self._a_uuid[:8]}  "
                f"b_leg={b_uuid[:8]}  route={route}"
            )

            clarify_streak = 0
            last_reply = ""

            for idx, spec in enumerate(specs, start=1):
                user_label = spec.label or spec.text
                wav_path = text_to_wav(spec.text)
                self._temp_dirs.append(os.path.dirname(wav_path))

                before_replies = watcher.count()
                self.inject_speech(wav_path, turn_idx=idx)

                reply_path = watcher.wait_for_new(timeout=50.0)
                if not reply_path:
                    problems.append(
                        f"  turn {idx}: no Vera reply wav within timeout "
                        f"(had {before_replies} replies before)"
                    )
                    turns.append(LiveTurn(
                        user_text=user_label,
                        user_wav=wav_path,
                        reply_wav="",
                        reply_text="",
                        stt_confidence=0.0,
                        problems=["no reply wav"],
                    ))
                    continue

                reply_text, conf = transcribe_wav(reply_path)
                turn_problems: List[str] = []

                if not reply_text:
                    turn_problems.append("empty STT on reply wav")
                if reply_text == last_reply and idx > 1:
                    turn_problems.append(f"exact repeat: {reply_text!r}")
                if ClarifyRe.search(reply_text):
                    clarify_streak += 1
                    if clarify_streak >= 3:
                        turn_problems.append(f"clarify loop x{clarify_streak}")
                else:
                    clarify_streak = 0
                if reply_text.rstrip(".") in (
                    MINIMAL_FALLBACK.rstrip("."),
                    "Услышала",
                ) and idx < len(specs):
                    turn_problems.append(f"dead-end ack: {reply_text!r}")
                if _ACTION_PROMISE_RE.search(reply_text) or looks_like_rescue_framing(
                    reply_text
                ):
                    turn_problems.append(f"promise/rescue: {reply_text!r}")
                if reply_looks_broken(reply_text):
                    turn_problems.append(f"broken reply: {reply_text!r}")

                user_size = 0
                user_glob = sorted(
                    glob.glob(os.path.join(MOSSVOICE_DIR, call_id, "user-*.wav"))
                )
                if user_glob:
                    try:
                        user_size = os.path.getsize(user_glob[-1])
                    except OSError:
                        user_size = 0
                if user_size < 4000 and spec.text.strip():
                    turn_problems.append(
                        f"user wav small ({user_size}B) — FS may not have heard speech"
                    )

                last_reply = reply_text
                problems.extend(
                    f"  turn {idx}: {p}" for p in turn_problems
                )
                turns.append(LiveTurn(
                    user_text=user_label,
                    user_wav=wav_path,
                    reply_wav=reply_path,
                    reply_text=reply_text,
                    stt_confidence=conf,
                    user_wav_size=user_size,
                    problems=turn_problems,
                ))

            # Scenario-specific checks
            if name == "bad_symptom":
                joined = " ".join(t.reply_text.lower() for t in turns)
                if not any(
                    w in joined
                    for w in (
                        "голов", "бол", "симптом", "терпим",
                        "беспокоит", "легче", "чувствуете",
                    )
                ):
                    problems.append("  expected symptom follow-up in Vera replies")
            if name == "critical_fall":
                joined = " ".join(t.reply_text for t in turns)
                if not SafetyRe.search(joined):
                    problems.append("  expected safety/record language after fall")
            if name == "goodbye":
                if turns and not GoodbyeRe.search(turns[-1].reply_text):
                    problems.append("  expected goodbye on closing turn")
            if name == "greeting_back" and turns:
                first = turns[0].reply_text.lower()
                greeting_back = any(
                    marker in first
                    for marker in ("и вам", "здравств", "доброго дня", "добрый")
                )
                if not greeting_back:
                    problems.append(
                        f"  expected greeting-back (и вам/здравствуйте): {turns[0].reply_text!r}"
                    )

        except Exception as exc:  # noqa: BLE001
            problems.append(f"  exception: {exc}")
        finally:
            if call_id:
                telephony_end_call(call_id)
            self.close()

        return ScenarioResult(
            name=name,
            call_id=call_id,
            channel_uuid=b_uuid,
            passed=len(problems) == 0 and len(turns) >= min(2, len(specs)),
            turns=turns,
            problems=problems,
            path_notes=path_notes,
        )


def _print_scenario(res: ScenarioResult) -> None:
    status = "PASS" if res.passed else "FAIL"
    print(f"\n{status}  {res.name}  call_id={res.call_id or '?'}")
    print(f"  path: {res.path_notes}")
    for i, tr in enumerate(res.turns, start=1):
        uw = os.path.basename(tr.user_wav) if tr.user_wav else "?"
        rw = os.path.basename(tr.reply_wav) if tr.reply_wav else "MISSING"
        print(f"  turn {i}:")
        print(f"    USER ({uw}): {tr.user_text}")
        print(f"    VERA ({rw}, conf={tr.stt_confidence:.2f}): {tr.reply_text}")
        if tr.user_wav_size:
            print(f"    captured user chunk: {tr.user_wav_size} bytes")
    for p in res.problems:
        print(p)


def _write_report(path: str, results: List[ScenarioResult], meta: dict) -> None:
    payload = {
        "meta": meta,
        "scenarios": [
            {
                "name": r.name,
                "call_id": r.call_id,
                "channel_uuid": r.channel_uuid,
                "passed": r.passed,
                "path_notes": r.path_notes,
                "problems": r.problems,
                "turns": [
                    {
                        "user": t.user_text,
                        "user_wav": t.user_wav,
                        "reply_wav": t.reply_wav,
                        "reply_text": t.reply_text,
                        "stt_confidence": t.stt_confidence,
                        "user_wav_size": t.user_wav_size,
                        "problems": t.problems,
                    }
                    for t in r.turns
                ],
            }
            for r in results
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Scenario name (repeatable). Default: good_path, bad_symptom, greeting_back, critical_fall, goodbye",
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--extension",
        default=os.environ.get("MOSS_TEST_EXTENSION", "4400"),
        help="FS extension: 4400=VoiceRuntime (prod), 4403=Lua test route",
    )
    parser.add_argument(
        "--originate",
        choices=("loopback", "bridge"),
        default="loopback",
        help="loopback/<ext> (default) or user/1000 bridge attempt",
    )
    parser.add_argument("--greeting-wait", type=float, default=14.0)
    parser.add_argument("--post-reply-wait", type=float, default=6.0)
    parser.add_argument("--report", default="", help="JSON report path")
    parser.add_argument(
        "--list-scenarios", action="store_true", help="List scenario names"
    )
    args = parser.parse_args(argv)

    if args.list_scenarios:
        for k in SCENARIOS:
            print(k)
        return 0

    print("=== Live Vera FS-path conversation tester ===")
    fs = fs_status()
    print(f"FreeSWITCH: {fs.split(chr(10))[0] if fs else 'unknown'}")
    try:
        health = telephony_health()
        print(
            f"Telephony: ok={health.get('ok')} active={health.get('calls_active')} "
            f"@ {TELEPHONY_URL}"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: telephony unreachable: {exc}")
        return 2
    if not health.get("ok"):
        print("ERROR: telephony unhealthy")
        return 2
    print(f"STT ready @ {STT_URL}: {stt_ready()}")

    stale_calls = telephony_cleanup_stale_calls()
    if stale_calls:
        print(f"Cleaned {stale_calls} stale telephony session(s) at capacity")

    names = args.scenario or [
        "good_path",
        "bad_symptom",
        "greeting_back",
        "critical_fall",
        "goodbye",
    ]
    for n in names:
        if n not in SCENARIOS:
            print(f"ERROR: unknown scenario {n!r}")
            return 2

    results: List[ScenarioResult] = []
    for name in names:
        print(f"\n--- Scenario: {name} ({len(SCENARIOS[name])} turns) ---")
        res: Optional[ScenarioResult] = None
        for attempt in (1, 2):
            if attempt > 1:
                print(f"  retry {attempt - 1} after cleanup...")
                telephony_cleanup_stale_calls()
                time.sleep(3.0)
            runner = LiveFsConversation(
                extension=args.extension,
                originate_mode=args.originate,
                greeting_wait=args.greeting_wait,
                post_reply_wait=args.post_reply_wait,
            )
            res = runner.run_scenario(name, SCENARIOS[name])
            if res.passed:
                break
        assert res is not None
        results.append(res)
        _print_scenario(res)
        if name != names[-1]:
            telephony_cleanup_stale_calls()
            time.sleep(2.0)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n=== LIVE FS SUMMARY: {passed}/{total} PASS ===")
    print(
        "Path: ESL originate → loopback/<ext> → VoiceRuntime/Lua → "
        "turn_stream → reply wav → host STT. NOT turn_text."
    )
    if args.extension == "4400":
        print(
            "Note: prod dialplan 4400 = answer+park + VoiceRuntime (Lua retired). "
            "Loopback caller audio via A-leg broadcast."
        )

    meta = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "telephony": TELEPHONY_URL,
        "stt": STT_URL,
        "extension": args.extension,
        "originate": args.originate,
        "fs_status_line": fs.split("\n")[0] if fs else "",
    }
    if args.report:
        _write_report(args.report, results, meta)
        print(f"Report: {args.report}")

    if args.strict and passed < total:
        failed = [r.name for r in results if not r.passed]
        print(f"FAILED scenarios: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
