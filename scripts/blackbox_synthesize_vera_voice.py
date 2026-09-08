#!/usr/bin/env python3
"""Synthesize black-box uplink WAV via IMVERA Silero TTS (Vera voice).

L3-A smoke only: Vera talks to herself through real SIP/RTP.
NOT a substitute for human voice bank (L3-B/L4).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import wave
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "assets" / "blackbox_voice" / "manifest.json"
WAV_DIR = ROOT / "tests" / "assets" / "blackbox_voice" / "wav"

# Default Russian text for every manifest phrase_id (merged with manifest.prompts).
DEFAULT_TEXTS: dict[str, str] = {
    "wellness_good_01": "Хорошо себя чувствую.",
    "wellness_good_02": "Всё хорошо.",
    "wellness_good_03": "Отлично себя чувствую.",
    "wellness_good_04": "Да хорошо вроде.",
    "wellness_good_05": "Чувствую себя хорошо.",
    "wellness_normal_01": "Нормально.",
    "wellness_normal_02": "Обычно.",
    "wellness_normal_03": "В целом нормально.",
    "wellness_normal_04": "Да нормально себя чувствую.",
    "wellness_normal_05": "Ничего особенного.",
    "wellness_so_so_01": "Так себе сегодня.",
    "wellness_so_so_02": "Не очень.",
    "wellness_so_so_03": "Сегодня так себе.",
    "wellness_so_so_04": "Неважно себя чувствую.",
    "wellness_so_so_05": "Ну такое.",
    "wellness_okay_01": "Пойдёт.",
    "wellness_okay_02": "Да пойдёт.",
    "wellness_okay_03": "Терпимо.",
    "wellness_okay_04": "Сойдёт.",
    "wellness_okay_05": "Более-менее.",
    "wellness_bad_01": "Плохо себя чувствую.",
    "wellness_bad_02": "Мне плохо.",
    "wellness_bad_03": "Сегодня плохо.",
    "wellness_bad_04": "Совсем не очень.",
    "wellness_bad_05": "Чувствую себя паршиво.",
    "mood_positive_01": "Настроение хорошее.",
    "mood_neutral_01": "Нормальное настроение.",
    "mood_negative_01": "Да не очень настроение.",
    "mood_uncertain_01": "Не знаю, какое настроение.",
    "sleep_good_01": "Спал хорошо.",
    "sleep_normal_01": "Спал нормально.",
    "sleep_bad_01": "Почти не спал.",
    "sleep_short_01": "Мало спал.",
    "plans_home_01": "Дома посижу.",
    "plans_walk_01": "Пойду гулять.",
    "plans_doctor_01": "Сегодня пойду в больницу.",
    "plans_none_01": "Планов нет.",
    "plans_uncertain_01": "Пока не знаю.",
    "goodbye_01": "До свидания.",
    "goodbye_confirm_01": "Да, спасибо.",
    "repair_allo_01": "Алло, ты меня слышишь?",
    "backchannel_01": "Хорошо.",
    "multi_slot_so_so_sleep_plans": (
        "Да так себе сегодня, почти не спал, после обеда в больницу пойду."
    ),
    "contextual_horosho_plans": "Хорошо.",
}

SMOKE_IDS = (
    "multi_slot_so_so_sleep_plans",
    "contextual_horosho_plans",
    "goodbye_01",
    "wellness_good_01",
    "repair_allo_01",
    "mood_positive_01",
    "sleep_normal_01",
    "plans_doctor_01",
    "backchannel_01",
)


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _phrase_text(data: dict, phrase_id: str) -> str:
    prompts = data.get("prompts") or {}
    if phrase_id in prompts and prompts[phrase_id].strip():
        return prompts[phrase_id].strip()
    if phrase_id in DEFAULT_TEXTS:
        return DEFAULT_TEXTS[phrase_id]
    raise KeyError(f"no text for phrase_id={phrase_id}")


def _synthesize_pcm(
    client: httpx.Client,
    tts_url: str,
    *,
    phrase_id: str,
    text: str,
) -> tuple[bytes, int]:
    pcm_parts: list[bytes] = []
    sample_rate = 24000
    with client.stream(
        "POST",
        f"{tts_url}/v1/synthesize",
        json={
            "call_id": "blackbox-synth",
            "generation_id": f"synth-{phrase_id}",
            "phrase_id": phrase_id,
            "text": text,
        },
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("done"):
                break
            if chunk.get("pcm_b64"):
                pcm_parts.append(base64.b64decode(chunk["pcm_b64"]))
                sample_rate = int(chunk.get("sample_rate", sample_rate))
    pcm = b"".join(pcm_parts)
    if not pcm:
        raise RuntimeError(f"TTS produced no PCM for {phrase_id}")
    return pcm, sample_rate


def _pcm_to_wav_16k(pcm_s16le: bytes, source_rate: int, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        src = Path(tmp.name)
    try:
        with wave.open(str(src), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(source_rate)
            wf.writeframes(pcm_s16le)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-ac",
                "1",
                "-ar",
                "16000",
                str(out_path),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        src.unlink(missing_ok=True)


def _check_tts(tts_url: str) -> str:
    r = httpx.get(f"{tts_url}/health/ready", timeout=5.0)
    r.raise_for_status()
    revision = str(r.json().get("model_revision", "")).strip()
    if "macos_say" in revision or not revision.startswith("silero_lab:silero:"):
        raise RuntimeError(f"TTS is not Silero lab ({revision!r})")
    return revision


def synthesize(
    *,
    phrase_ids: list[str] | None = None,
    tts_url: str | None = None,
    update_manifest: bool = True,
) -> list[Path]:
    data = _load_manifest()
    phrases = data.get("phrases") or {}
    all_ids = phrase_ids or sorted(phrases.keys())
    base_url = (tts_url or os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")).rstrip("/")
    revision = _check_tts(base_url)

    written: list[Path] = []
    prompts = dict(data.get("prompts") or {})
    timeout = httpx.Timeout(10.0, read=60.0)
    with httpx.Client(timeout=timeout) as client:
        for phrase_id in all_ids:
            if phrase_id not in phrases:
                print(f"SKIP unknown phrase_id: {phrase_id}", file=sys.stderr)
                continue
            text = _phrase_text(data, phrase_id)
            prompts[phrase_id] = text
            pcm, sr = _synthesize_pcm(client, base_url, phrase_id=phrase_id, text=text)
            out = WAV_DIR / Path(phrases[phrase_id]).name
            _pcm_to_wav_16k(pcm, sr, out)
            written.append(out)
            print(f"  {phrase_id} → {out.name} ({len(pcm)} bytes @ {sr} Hz)")

    if update_manifest:
        data["prompts"] = prompts
        data["source"] = "vera_tts_smoke"
        data["synthesized_at"] = datetime.now(UTC).isoformat()
        data["tts_model_revision"] = revision
        data["notes"] = (
            "L3-A smoke: uplink WAV synthesized via IMVERA Silero TTS (Vera voice). "
            "NOT human speech — L3-B/L4 require 2–3 human speakers."
        )
        MANIFEST.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize black-box WAV via Vera TTS")
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Synthesize minimum smoke set (gate still needs all manifest files)",
    )
    parser.add_argument(
        "--phrase",
        action="append",
        dest="phrases",
        metavar="PHRASE_ID",
        help="Synthesize one phrase (repeatable)",
    )
    parser.add_argument(
        "--list-smoke",
        action="store_true",
        help="List smoke phrase IDs",
    )
    args = parser.parse_args()

    if args.list_smoke:
        for pid in SMOKE_IDS:
            print(pid)
        return 0

    data = _load_manifest()
    phrase_ids = args.phrases
    if args.smoke_only:
        phrase_ids = list(SMOKE_IDS)
    elif phrase_ids is None:
        phrase_ids = sorted((data.get("phrases") or {}).keys())

    print(f"Synthesizing {len(phrase_ids)} phrase(s) via IMVERA TTS (Vera/Silero)...")
    try:
        paths = synthesize(phrase_ids=phrase_ids)
    except (httpx.HTTPError, RuntimeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1

    missing = [
        pid
        for pid in sorted((data.get("phrases") or {}).keys())
        if not (WAV_DIR / Path(data["phrases"][pid]).name).is_file()
    ]
    if missing:
        print(
            f"\nWARN: {len(missing)} manifest WAV still missing — run without --smoke-only:",
            file=sys.stderr,
        )
        print("  python3 scripts/blackbox_synthesize_vera_voice.py", file=sys.stderr)
    else:
        print(f"\nOK: all {len(paths)} manifest WAV present (vera_tts_smoke)")
    print("NOTE: This is L3-A Vera-self SIP smoke, NOT production voice acceptance.")
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
