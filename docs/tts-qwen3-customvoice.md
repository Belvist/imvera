# Qwen3-TTS CustomVoice (MLX) — lab notes

Model: `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit`  
Worker: `services/tts/worker.py`  
Config: `config/voice-m5.yaml`  
Voice refs: `config/voice_refs/` + `manifest.json`

## Default (2026-09-07) — warmer, less mocky

Lab default is **preset `serena` + warm `instruct`**, cloning **off** (`use_ref: false`).

Why: zero-shot FLEURS clone on CustomVoice often sounds uncanny or «как будто прикалываются» — mlx_audio warns cloning is unreliable on CustomVoice checkpoints.

| Parameter | Default | Notes |
|-----------|---------|--------|
| `voice` | `serena` | Female preset |
| `use_ref` | `false` | Enable clone via config or env |
| `generation.temperature` | `0.65` | Lower than mlx default 0.9 |
| `generation.speed` | `0.95` | Slightly slower |
| `generation.instruct` | warm Russian | No irony / caricature |

## Built-in presets (`voice` in config)

Verified via `mlx_audio` `Model.generate(voice=..., lang_code="Russian")`:

| Preset | Notes |
|--------|--------|
| `serena` | Female — **lab default** |
| `vivian` | Female — alternate preset |
| `ono_anna` | Female (Japanese-tuned name; Russian not evaluated) |
| `sohee` | Female (Korean-tuned) |
| `ryan`, `aiden`, `eric`, `dylan`, `uncle_fu` | Male |

**NOT VERIFIED:** which preset is best for elderly Russian phone speech. Per `ai-model-evaluation` skill, run internal listen test (≥3 raters) before production claim.

## Engines (`tts.engine`)

| Engine | Model | Use |
|--------|-------|-----|
| `mlx_customvoice` | CustomVoice-8bit | Default lab — presets + optional clone |
| `mlx_base_clone` | Base-bf16 | Workbench `reference_clone` path — better cloning |
| `silero_lab` | Silero v5_5_ru kseniya | **NC license — local lab only** |

Silero requires `IMVERA_SILERO_LAB_ACK=1` and `pip install -e ".[lab-silero]"`. See ADR-002.

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

### Bundled Russian female references

| ID | Kind | License | Notes |
|----|------|---------|--------|
| `bootstrap_serena_ru` | Bootstrap | project-bootstrap | **Default ref** when cloning enabled |
| `bootstrap_vivian_ru` | Bootstrap | project-bootstrap | Vera greeting phrase |
| `fleurs_ru_female_1` | Human | CC-BY-4.0 | Previous default — often sounds uncanny on CustomVoice |
| `fleurs_ru_female_2` | Human | CC-BY-4.0 | Alternate FLEURS clip |

See `config/voice_refs/manifest.json` for `ref_text`, duration, attribution.

### Config

```yaml
tts:
  engine: mlx_customvoice
  voice: serena
  use_ref: false
  ref_id: bootstrap_serena_ru
  generation:
    temperature: 0.65
    speed: 0.95
    instruct: "Тёплый спокойный голос без иронии..."
```

When `use_ref: true` (or `IMVERA_TTS_USE_REF=1`) and ref resolves, preset timbre is overridden by clone.

### Environment overrides

| Variable | Effect |
|----------|--------|
| `IMVERA_TTS_ENGINE` | `mlx_customvoice` \| `mlx_base_clone` \| `silero_lab` |
| `IMVERA_TTS_REF_ID` | Manifest ref id (loads file + `ref_text`) |
| `IMVERA_TTS_REF_AUDIO` | Path to WAV (repo-relative or absolute) |
| `IMVERA_TTS_REF_TEXT` | Transcript for env audio path |
| `IMVERA_TTS_USE_REF` | `1` / `0` — enable/disable cloning from config |
| `IMVERA_TTS_TEMPERATURE` | Override sampling temperature |
| `IMVERA_TTS_SPEED` | Override speed |
| `IMVERA_TTS_INSTRUCT` | Override style instruct |
| `IMVERA_SILERO_LAB_ACK` | Must be `1` to enable Silero lab engine |

### Preview & A/B compare

```bash
make tts-preview-list
make tts-preview
make tts-preview-compare
python scripts/tts_preview.py --no-ref --preset serena --out /tmp/vera.wav
python scripts/tts_preview.py --ref-id fleurs_ru_female_1 --out /tmp/fleurs.wav
python scripts/tts_compare.py --out /tmp/imvera_tts_compare
IMVERA_SILERO_LAB_ACK=1 python scripts/tts_compare.py --include-silero
```

Open `/tmp/imvera_tts_compare/listen.html` for side-by-side listen test.

### Production gate

1. Replace bootstrap refs with **licensed** talent recordings (or documented consent path).
2. Benchmark vs presets on phone-bandwidth fixtures (`tools/voice_lab/`).
3. Internal MOS listen test (≥3 raters) per `ai-model-evaluation` skill.
4. ADR + license check before pilot claim. **Silero NC is not a production path.**
