"""Vera demo builder: grandma's real voice + live dialogue + Vera TTS → MP4.

Usage:
    python3 tools/vera_demo/build_demo.py [--only trevoga]

For each scenario: runs the real CallSession turn by turn over the
grandmother's transcribed phrases, synthesizes Vera's actual replies
(silero/kseniya via :9102), interleaves [Vera opening, g0, Vera, g1, ...],
and muxes to .mp4 (AAC). Grandmother's audio is never altered.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from services.tts.http_provider import HttpTTSProvider

DEMO = _ROOT / ".run" / "vera_demo"
OUT = Path("/Users/earflow/Downloads")

SCENARIOS = {
    "nuzhno": {
        "title": "Нужно внимание",
        "turns": [
            "Привет.",
            "Да не очень, голова болит.",
            "Утром как проснулась.",
            "Боль, ну, терпимая.",
            "Нет, всё хорошо.",
            "Только голова болит вот.",
            "Ну, пока.",
        ],
    },
    "poryadke": {
        "title": "Все в порядке",
        "turns": [
            "Привет.",
            "Всё хорошо, только что покушала.",
            "Да, было вкусно.",
            "Да, от давления.",
            "Да, приняла.",
            "Всё хорошо.",
            "Да, выспалась.",
            "Нет, всё хорошо.",
            "С подружками гулять пойду. Пока.",
        ],
    },
    "trevoga": {
        "title": "Тревога",
        "turns": [
            "Ой, плохо.",
            "Сердце болит и давление.",
            "Ой, сегодня в 12:00.",
            "Как будто, чтобы родственники позвонили и вызвали скорую.",
            "Ой, ну ладно, пока.",
        ],
    },
}


async def _vera_say(tts: HttpTTSProvider, text: str, tag: str) -> Path:
    pcm = b""
    async for ch in tts.synthesize(
        text, call_id="demo", generation_id=f"g-{tag}",
        phrase_id=f"p-{tag}", deadline=time.monotonic() + 120,
    ):
        pcm += ch.pcm_s16le
    raw = DEMO / f"vera_{tag}.s16le"
    raw.write_bytes(pcm)
    wav = DEMO / f"vera_{tag}.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", "24000",
         "-ac", "1", "-i", str(raw), "-ar", "16000", str(wav)],
        check=True,
    )
    return wav


def _run_dialogue(key: str, turns: list[str]) -> list[str]:
    """Real CallSession; returns Vera's speeches [opening, r1, ...].

    Demo config: full check-in (mission requires background goals) so the
    conversation covers mood/sleep/plans like live calls. Grandmother's
    audio is never altered; only Vera's replies are synthesized.
    """
    session = CallSession(
        call_id=f"demo-{key}", family_id="demo-family",
        elder_display_name="Тамара Андреевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    if session._engine is not None:
        session._engine.state.required_background_goals = {"mood", "sleep", "plans"}
    speeches = [opening.proposal.speech or ""]
    session.mark_spoken_action(opening.proposal.generation_id)
    for text in turns:
        result = session.handle_user_text(text)
        speech = result.proposal.speech or ""
        if not speech.strip() and result.proposal.intent == "wait_for_continuation":
            waited = session.handle_wait_expired()
            speech = waited.proposal.speech or ""
            session.mark_spoken_action(waited.proposal.generation_id)
        else:
            session.mark_spoken_action(result.proposal.generation_id)
        speeches.append(speech)
    return speeches


async def _build(key: str, title: str, turns: list[str]) -> Path:
    tts = HttpTTSProvider("http://127.0.0.1:9102")
    speeches = _run_dialogue(key, turns)
    print(f"== {title}: Vera says:")
    for i, s in enumerate(speeches):
        print(f"  [v{i}] {s}")

    parts: list[Path] = []
    v_open = await _vera_say(tts, speeches[0], f"{key}_v0")
    parts.append(v_open)
    n_gran = len([p for p in DEMO.glob(f"{key}_s*.wav")])
    for i in range(n_gran):
        parts.append(DEMO / f"{key}_s{i}.wav")
        if i + 1 < len(speeches) and speeches[i + 1].strip():
            parts.append(await _vera_say(tts, speeches[i + 1], f"{key}_v{i+1}"))

    gap = DEMO / "gap.wav"
    if not gap.exists():
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
             "-i", "anullsrc=r=16000:cl=mono:d=0.5", "-c:a", "pcm_s16le", str(gap)],
            check=True,
        )
    mix = DEMO / f"{key}_mix.wav"
    inputs = []
    for p in parts:
        inputs += ["-i", str(p), "-i", str(gap)]
    n = len(parts) * 2
    filt = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *inputs,
         "-filter_complex", filt, "-map", "[out]", "-c:a", "pcm_s16le", str(mix)],
        check=True,
    )
    mp4 = OUT / f"Вера — {title}.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(mix),
         "-c:a", "aac", "-b:a", "128k", str(mp4)],
        check=True,
    )
    return mp4


async def main(only: str | None) -> None:
    for key, sc in SCENARIOS.items():
        if only and key != only:
            continue
        mp4 = await _build(key, sc["title"], sc["turns"])
        print("saved", mp4, f"({mp4.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    asyncio.run(main(only))
