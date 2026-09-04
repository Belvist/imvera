#!/usr/bin/env python3
"""Live telephony E2E harness — HTTP path identical to Lua → agent.

Exercises POST /calls → /turn_text or /turn (audio) → /end against a running
telephony daemon (default http://127.0.0.1:9400). turn_text bypasses STT but
uses the same ConversationFacade/orchestrator dialogue path as live calls.
Silent/noisy WAV turns exercise the full STT → gate → plan pipeline.

Run:
    python3 voice-lab/e2e_live_calls.py
    python3 voice-lab/e2e_live_calls.py --base http://127.0.0.1:9400 --strict

Honest limits (documented in report):
    - Cannot drive Zoiper GUI; loopback originate is optional (--fs-loopback).
    - Loopback calls have paired-leg echo artefacts; HTTP E2E is primary.
    - turn_text scenarios skip STT variance; audio scenarios depend on host STT.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import struct
import sys
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Literal, Optional, Sequence, Tuple

import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_TELEPHONY = os.path.join(os.path.dirname(_HERE), "telephony")
sys.path.insert(0, _TELEPHONY)

from conversation_system.reply.guards import (  # noqa: E402
    _ACTION_PROMISE_RE,
    looks_like_rescue_framing,
    reply_looks_broken,
    MINIMAL_FALLBACK,
)

TurnMode = Literal["text", "silent", "tone"]
AnchorRe = re.compile(r"хорошо\s+или\s+плохо", re.IGNORECASE)
ClarifyBareRe = re.compile(
    r"^(Услышала вас\.?|Повторите[,.]?\s*пожалуйста\.?)$",
    re.IGNORECASE,
)
GoodbyeRe = re.compile(
    r"(до\s+свидания|всего\s+доброго|берегите\s+себя|хорошего\s+дня)",
    re.IGNORECASE,
)
SafetyRe = re.compile(
    r"(записала|близкие\s+увидят|перестраховал|тревожн|симптом|болит|упал)",
    re.IGNORECASE,
)


def _wav_bytes(*, amplitude: int = 0, frames: int = 1600, rate: int = 16000) -> bytes:
    body = struct.pack(f"<{frames}h", *([amplitude] * frames))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(body)
    return buf.getvalue()


def _tone_wav(seconds: float = 1.0, freq: float = 440.0, rate: int = 16000) -> bytes:
    import math

    n = int(seconds * rate)
    samples = [
        int(8000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)
    ]
    body = struct.pack(f"<{n}h", *samples)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(body)
    return buf.getvalue()


@dataclass
class TurnSpec:
    """One user turn in a scenario."""

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


@dataclass
class ScenarioResult:
    name: str
    call_id: str
    passed: bool
    problems: List[str] = field(default_factory=list)
    turns: List[TurnResult] = field(default_factory=list)


class TelephonyClient:
    def __init__(self, base: str, timeout: float = 90.0) -> None:
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
        if not body.get("ok"):
            raise RuntimeError(f"new_call failed: {body}")
        return str(body["call_id"]), str(body.get("greeting") or "")

    def turn_text(self, call_id: str, text: str) -> dict:
        return self._request(
            "POST",
            f"/calls/{call_id}/turn_text",
            json.dumps({"text": text}).encode(),
        )

    def turn_audio(self, call_id: str, wav: bytes) -> dict:
        payload = json.dumps({"audio_b64": base64.b64encode(wav).decode()}).encode()
        return self._request("POST", f"/calls/{call_id}/turn", payload)

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
        or "повторите" in reply.lower()
        or "слышите" in reply.lower()
    )
    if is_clarify:
        clarify_streak += 1
        if clarify_streak > 2:
            problems.append(
                f"  turn {turn_idx}: CLARIFY loop >2: {reply!r}"
            )
    else:
        clarify_streak = 0

    mid_call = turn_idx < total_turns
    if mid_call and reply.rstrip(".") == MINIMAL_FALLBACK.rstrip("."):
        problems.append(
            f"  turn {turn_idx}: bare minimal fallback mid-call: {reply!r}"
        )
    if mid_call and "?" not in reply and reply.lower().startswith("услышала"):
        problems.append(
            f"  turn {turn_idx}: bare heard-ack without question: {reply!r}"
        )

    return problems, clarify_streak


def _run_turns(
    client: TelephonyClient,
    call_id: str,
    specs: Sequence[TurnSpec],
) -> Tuple[List[TurnResult], List[str]]:
    results: List[TurnResult] = []
    problems: List[str] = []
    clarify_streak = 0

    for idx, spec in enumerate(specs, start=1):
        if spec.mode == "text":
            body = client.turn_text(call_id, spec.text)
            user_label = spec.label or spec.text
            transcript = spec.text
        else:
            wav = _wav_bytes() if spec.mode == "silent" else _tone_wav()
            body = client.turn_audio(call_id, wav)
            user_label = spec.label or f"<{spec.mode}-audio>"
            transcript = body.get("transcript")
            if transcript is None:
                transcript = ""

        if not body.get("ok", True) and body.get("error"):
            problems.append(f"  turn {idx}: API error: {body.get('error')}")
            continue

        reply = str(body.get("reply") or "").strip()
        finished = bool(body.get("finished"))
        tr = TurnResult(
            user=user_label,
            reply=reply,
            transcript=transcript if isinstance(transcript, str) else None,
            finished=finished,
            mode=spec.mode,
        )
        results.append(tr)

        turn_problems, clarify_streak = _global_turn_checks(
            idx, tr, clarify_streak=clarify_streak, total_turns=len(specs)
        )
        problems.extend(turn_problems)

        if finished and idx < len(specs):
            problems.append(
                f"  turn {idx}: call finished early (expected more turns)"
            )
            break

    return results, problems


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


def _check_safety_path(turns: List[TurnResult]) -> List[str]:
    replies = " ".join(t.reply for t in turns)
    if not SafetyRe.search(replies):
        return ["  expected safety/record language after fall report"]
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


def _check_short_yes_advances(turns: List[TurnResult]) -> List[str]:
    if len(turns) < 2:
        return ["  need wellness + short yes"]
    if turns[-1].reply.strip() == MINIMAL_FALLBACK:
        return ["  short yes got minimal fallback"]
    return []


def _check_narrative_not_forced(turns: List[TurnResult]) -> List[str]:
    if not turns:
        return ["  no turns"]
    first = turns[0].reply.lower()
    forced = ("как вы спали", "как сон", "как настроение", "чем планируете")
    if any(f in first for f in forced) and "внуч" not in first:
        return [f"  narrative answered with forced agenda jump: {turns[0].reply!r}"]
    return []


def _check_positive_wellness(turns: List[TurnResult]) -> List[str]:
    return _check_no_safety_alert(turns)


def _check_family_question(turns: List[TurnResult]) -> List[str]:
    joined = " ".join(t.reply for t in turns).lower()
    if "родн" not in joined and "близк" not in joined and "?" not in joined:
        return ["  expected family-related prompt in replies"]
    return []


def _check_agenda_moves(turns: List[TurnResult]) -> List[str]:
    if len(turns) < 3:
        return []
    questions = [t.reply for t in turns if "?" in t.reply]
    if len(questions) < 2:
        return ["  expected multiple agenda questions across turns"]
    if len(set(questions)) < 2:
        return ["  agenda questions did not vary (possible stuck topic)"]
    return []


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


SCENARIOS: List[Tuple[str, Sequence[TurnSpec], Tuple[ScenarioCheck, ...]]] = [
    _scenario(
        "01_good_path",
        [
            TurnSpec("хорошо себя чувствую"),
            TurnSpec("хорошее настроение"),
            TurnSpec("спала нормально"),
            TurnSpec("пойду в магазин"),
            TurnSpec("да"),
        ],
        _check_agenda_moves,
        _check_no_safety_alert,
    ),
    _scenario(
        "02_symptom_bad",
        [
            TurnSpec("плохо"),
            TurnSpec("болит голова"),
            TurnSpec("терпимо"),
            TurnSpec("утром"),
        ],
        _check_symptom_followup,
    ),
    _scenario(
        "03_fall_safety",
        [TurnSpec("я упал")],
        _check_safety_path,
    ),
    _scenario(
        "04_silence_ladder",
        [
            TurnSpec("", mode="silent", label="<silence>"),
            TurnSpec("", mode="silent", label="<silence>"),
            TurnSpec("хорошо", mode="text"),
        ],
        _check_first_silence_not_anchor,
    ),
    _scenario(
        "05_goodbye_close",
        [
            TurnSpec("всё хорошо"),
            TurnSpec("до свидания"),
        ],
        _check_finished,
    ),
    _scenario(
        "06_repair_what",
        [
            TurnSpec("всё хорошо"),
            TurnSpec("что?"),
            TurnSpec("хорошо"),
        ],
        _check_repair,
    ),
    _scenario(
        "07_short_yes_wellness",
        [
            TurnSpec("нормально"),
            TurnSpec("да"),
        ],
        _check_short_yes_advances,
    ),
    _scenario(
        "08_narrative_story",
        [
            TurnSpec(
                "Внучка приезжала, мы чай пили на кухне и долго разговаривали"
            ),
            TurnSpec("да"),
        ],
        _check_narrative_not_forced,
    ),
    _scenario(
        "09_positive_no_red",
        [
            TurnSpec("отлично, ничего не болит"),
            TurnSpec("настроение хорошее"),
        ],
        _check_positive_wellness,
    ),
    _scenario(
        "10_critical_wellness_words",
        [
            TurnSpec("голова сильно болит"),
            TurnSpec("да"),
        ],
        _check_symptom_followup,
    ),
    _scenario(
        "11_greeting_back",
        [
            TurnSpec("здравствуйте"),
            TurnSpec("хорошо"),
        ],
        _check_greeting_back,
    ),
    _scenario(
        "12_refusal_wrap",
        [
            TurnSpec("всё нормально"),
            TurnSpec("нет, спасибо"),
        ],
    ),
    _scenario(
        "13_negated_fall",
        [
            TurnSpec("я не упал"),
            TurnSpec("всё хорошо"),
        ],
        _check_negated_fall_ok,
    ),
    _scenario(
        "14_side_question",
        [
            TurnSpec("какое сегодня число?"),
            TurnSpec("спасибо"),
            TurnSpec("всё хорошо"),
        ],
    ),
    _scenario(
        "15_audio_tone_turn",
        [
            TurnSpec("всё хорошо"),
            TurnSpec("", mode="tone", label="<tone-audio>"),
        ],
    ),
    _scenario(
        "16_low_conf_recovery",
        [
            TurnSpec("", mode="silent", label="<silence>"),
            TurnSpec("хорошо"),
        ],
    ),
    _scenario(
        "17_wellness_medium",
        [
            TurnSpec("ну так себе"),
            TurnSpec("устала немного"),
            TurnSpec("спала прерывисто"),
        ],
        _check_agenda_moves,
    ),
]


def run_scenario(
    client: TelephonyClient,
    name: str,
    turns: Sequence[TurnSpec],
    checks: Sequence[ScenarioCheck],
) -> ScenarioResult:
    call_id, greeting = client.new_call()
    problems: List[str] = []
    if not greeting:
        problems.append("  missing greeting on new_call")

    turn_results, turn_problems = _run_turns(client, call_id, turns)
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
        print(f"    U: {user}")
        print(f"    V: {reply}")
    for p in res.problems:
        print(p)


def _optional_fs_loopback() -> Tuple[bool, str]:
    import shutil
    import subprocess

    fs_cli = shutil.which("fs_cli")
    if not fs_cli:
        return False, "fs_cli not found — skip loopback originate"
    cmd = [
        fs_cli,
        "-x",
        "originate loopback/4400/default 4400 XML default",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, out.strip() or f"exit {proc.returncode}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=os.environ.get("MOSS_TELEPHONY_URL", "http://127.0.0.1:9400"),
        help="Telephony base URL",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any scenario fails",
    )
    parser.add_argument(
        "--fs-loopback",
        action="store_true",
        help="Also fire one FreeSWITCH loopback originate (best-effort)",
    )
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

    print(f"Telephony OK @ {args.base}  components={health.get('components')}")

    results: List[ScenarioResult] = []
    for name, turns, checks in SCENARIOS:
        try:
            res = run_scenario(client, name, turns, checks)
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
    print(f"=== E2E SUMMARY: {passed}/{total} PASS ===")

    if args.fs_loopback:
        ok, msg = _optional_fs_loopback()
        print(f"FS loopback originate: {'OK' if ok else 'SKIP/FAIL'} — {msg}")

    print(
        "\nLimits: Zoiper GUI not automated; loopback has echo-leg artefacts; "
        "turn_text skips STT; audio turns depend on host STT quality."
    )

    if args.strict and passed < total:
        failed = [r.name for r in results if not r.passed]
        print(f"FAILED: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
