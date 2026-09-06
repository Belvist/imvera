#!/usr/bin/env python3
"""A/B local TTS comparison — presets, clones, optional Silero lab (NC)."""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path

from services.tts.preview import synthesize_preview

COMPARE_VARIANTS: list[dict[str, str | bool | None]] = [
    {
        "id": "preset_serena_warm",
        "label": "Qwen CustomVoice preset serena + warm instruct",
        "preset": "serena",
        "no_ref": True,
    },
    {
        "id": "preset_vivian_warm",
        "label": "Qwen CustomVoice preset vivian + warm instruct",
        "preset": "vivian",
        "no_ref": True,
    },
    {
        "id": "clone_bootstrap_serena",
        "label": "Clone bootstrap_serena_ru (Vera phrase)",
        "ref_id": "bootstrap_serena_ru",
    },
    {
        "id": "clone_bootstrap_vivian",
        "label": "Clone bootstrap_vivian_ru (Vera phrase)",
        "ref_id": "bootstrap_vivian_ru",
    },
    {
        "id": "clone_fleurs_1",
        "label": "Clone fleurs_ru_female_1 (previous default)",
        "ref_id": "fleurs_ru_female_1",
    },
    {
        "id": "clone_fleurs_2",
        "label": "Clone fleurs_ru_female_2 (alternate FLEURS)",
        "ref_id": "fleurs_ru_female_2",
    },
    {
        "id": "base_clone_bootstrap_serena",
        "label": "Base model clone bootstrap_serena_ru",
        "ref_id": "bootstrap_serena_ru",
        "engine": "mlx_base_clone",
    },
    {
        "id": "silero_kseniya_lab",
        "label": "Silero v5_5_ru kseniya (NC — lab only)",
        "engine": "silero_lab",
    },
]

DEFAULT_TEXT = (
    "Здравствуйте. Меня зовут Вера. Я звоню, чтобы узнать, как вы себя чувствуете сегодня. "
    "Можно не торопиться с ответом."
)


def _write_gallery(out_dir: Path, rows: list[dict]) -> None:
    cards = []
    for row in rows:
        status = row.get("status", "ok")
        if status == "ok":
            audio_tag = f'<audio controls preload="none" src="{html.escape(row["file"])}"></audio>'
        else:
            audio_tag = f'<p class="err">{html.escape(str(row.get("error", "failed")))}</p>'
        cards.append(
            "<article>"
            f"<h2>{html.escape(row['label'])}</h2>"
            f"<p><code>{html.escape(row['id'])}</code></p>"
            f"{audio_tag}"
            f"<p>{html.escape(row.get('duration_s', ''))}</p>"
            "</article>"
        )
    doc = (
        "<!doctype html><html lang='ru'><meta charset='utf-8'>"
        "<title>IMVERA TTS A/B</title>"
        "<style>body{font:17px system-ui;max-width:900px;margin:40px auto;padding:20px;"
        "background:#f7f5ef;color:#172822}article{background:#fff;border-radius:16px;"
        "padding:20px;margin:18px 0}audio{width:100%}.err{color:#8b1a1a}</style>"
        "<h1>IMVERA — сравнение голосов TTS</h1>"
        "<p>Субъективная прослушка. Silero — только lab (CC BY-NC-SA). "
        "FLEURS clone на CustomVoice часто звучит неестественно.</p>"
        + "".join(cards)
        + "</html>"
    )
    (out_dir / "listen.html").write_text(doc, encoding="utf-8")


def run_compare(
    text: str,
    out_dir: Path,
    *,
    include_silero: bool,
    variants: list[dict] | None = None,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    selected = variants or COMPARE_VARIANTS
    rows: list[dict] = []
    manifest_rows: list[dict] = []
    errors = 0

    for variant in selected:
        vid = str(variant["id"])
        if vid == "silero_kseniya_lab" and not include_silero:
            continue
        wav_name = f"{vid}.wav"
        wav_path = out_dir / wav_name
        row: dict = {"id": vid, "label": str(variant["label"]), "file": wav_name}
        started = time.monotonic()
        try:
            mode = synthesize_preview(
                text,
                wav_path,
                ref_id=str(variant["ref_id"]) if variant.get("ref_id") else None,
                preset=str(variant["preset"]) if variant.get("preset") else None,
                use_ref=False if variant.get("no_ref") else None,
                engine=str(variant["engine"]) if variant.get("engine") else None,
            )
            import soundfile as sf

            info = sf.info(wav_path)
            row["status"] = "ok"
            row["mode"] = mode
            row["duration_s"] = f"{info.duration:.2f}s @ {info.samplerate}Hz"
            row["generation_seconds"] = round(time.monotonic() - started, 2)
            print(f"OK {vid}: {mode}")
        except Exception as exc:
            row["status"] = "error"
            row["error"] = str(exc)
            errors += 1
            print(f"FAILED {vid}: {exc}", file=sys.stderr)
        rows.append(row)
        manifest_rows.append({**row, "text": text})

    _write_gallery(out_dir, rows)
    (out_dir / "manifest.json").write_text(
        json.dumps({"text": text, "variants": manifest_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {out_dir / 'listen.html'} ({len(rows)} variants, {errors} errors)")
    return 1 if errors and errors == len(rows) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--out", type=Path, default=Path("/tmp/imvera_tts_compare"))
    parser.add_argument(
        "--include-silero",
        action="store_true",
        help="Include Silero kseniya (requires IMVERA_SILERO_LAB_ACK=1 and torch)",
    )
    parser.add_argument("--list", action="store_true", help="List compare variants and exit")
    args = parser.parse_args()

    if args.list:
        for v in COMPARE_VARIANTS:
            print(f"{v['id']:28} {v['label']}")
        return 0

    return run_compare(args.text, args.out, include_silero=args.include_silero)


if __name__ == "__main__":
    raise SystemExit(main())
