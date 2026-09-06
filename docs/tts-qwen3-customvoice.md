# Qwen3-TTS CustomVoice (MLX) — lab notes

Model: `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit`  
Worker: `services/tts/worker.py`  
Config: `config/voice-m5.yaml`  
Voice refs: `config/voice_refs/` + `manifest.json`

## Built-in presets (`voice` in config)

Verified via `mlx_audio` `Model.generate(voice=..., lang_code="Russian")`:

| Preset | Notes |
|--------|--------|
| `serena` | Female |
| `vivian` | Female — lab preset fallback when cloning disabled |
| `ono_anna` | Female (Japanese-tuned name; Russian not evaluated) |
| `sohee` | Female (Korean-tuned) |
| `ryan`, `aiden`, `eric`, `dylan`, `uncle_fu` | Male |

**NOT VERIFIED:** which preset is best for elderly Russian phone speech. Per `ai-model-evaluation` skill, run internal listen test (≥3 raters) before production claim.

## Voice cloning (`ref_audio` + `ref_text`)

`mlx_audio` CustomVoice supports **zero-shot** cloning via reference audio (not training).  
`mlx_audio` prints a warning that cloning is **not fully reliable** on CustomVoice checkpoints — treat as lab feature.

### Reference audio requirements (Qwen3-TTS / mlx_audio)

| Parameter | Requirement |
|-----------|-------------|
| Duration | 3–10 s recommended (up to ~15 s in docs) |
| Format | Mono WAV PCM16 (MP3/FLAC OK; worker path uses WAV) |
| Sample rate | Any — `mlx_audio.utils.load_audio` resamples to **24 kHz** |
| Content | Single female speaker, no music/TV/overlap |
| `ref_text` | **Required** for ICL mode — must match spoken words in ref |
| Quality | Clean speech; accurate transcript beats longer noisy clip |

### Bundled Russian female references (no user WAV needed)

Prepared by `make voice-refs-prepare` / `scripts/prepare_voice_refs.py`:

| ID | Kind | License | Notes |
|----|------|---------|--------|
| `fleurs_ru_female_1` | Human | CC-BY-4.0 | **Default** — FLEURS `ru_ru`, gender=female |
| `fleurs_ru_female_2` | Human | CC-BY-4.0 | Alternate FLEURS clip |
| `bootstrap_vivian_ru` | Bootstrap | project-bootstrap | Synthesized from `vivian` preset — replace for prod |
| `bootstrap_serena_ru` | Bootstrap | project-bootstrap | Synthesized from `serena` preset — replace for prod |

See `config/voice_refs/manifest.json` for `ref_text`, duration, attribution.

**Honest scope:** this is zero-shot cloning, not a fine-tuned Vera model. Quality varies; bootstrap refs are a dev fallback only.

### Config

```yaml
tts:
  voice: vivian          # preset fallback when cloning off
  ref_id: fleurs_ru_female_1
  ref_audio: config/voice_refs/fleurs_ru_female_1.wav
  ref_text: "эта идея пришла из китая где излюбленным цветком был цвет сливы"
```

When `ref_audio` + `ref_text` resolve and file exists, preset `voice` is ignored for timbre (still passed to mlx).

### Environment overrides

| Variable | Effect |
|----------|--------|
| `IMVERA_TTS_REF_ID` | Manifest ref id (loads file + `ref_text`) |
| `IMVERA_TTS_REF_AUDIO` | Path to WAV (repo-relative or absolute) |
| `IMVERA_TTS_REF_TEXT` | Transcript for env audio path |
| `IMVERA_TTS_USE_REF=0` | Disable cloning; use preset `voice` only |

Resolution order: env ref id → env audio → config `ref_id` → config `ref_audio` → manifest `default_ref`.

### Preview

```bash
make tts-preview-list
make tts-preview
python scripts/tts_preview.py --ref-id bootstrap_vivian_ru --out /tmp/vera.wav
python scripts/tts_preview.py --worker http://127.0.0.1:9102 --out /tmp/worker.wav
```

### Production gate

1. Replace bootstrap refs with **licensed** talent recordings (or CC0/Common Voice with documented consent path).
2. Benchmark vs presets on phone-bandwidth fixtures (`tools/voice_lab/`).
3. Internal MOS listen test (≥3 raters) per `ai-model-evaluation` skill.
4. ADR + license check before pilot claim.
