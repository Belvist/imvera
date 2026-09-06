# Qwen3-TTS CustomVoice (MLX) — lab notes

Model: `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit`  
Worker: `services/tts/worker.py`  
Config: `config/voice-m5.yaml`

## Built-in presets (`voice` in config)

Verified via `mlx_audio` `Model.generate(voice=..., lang_code="Russian")`:

| Preset | Notes |
|--------|--------|
| `serena` | Female, default in early lab |
| `vivian` | Female — **current lab default** (subjective; no MOS benchmark yet) |
| `ono_anna` | Female (Japanese-tuned name; Russian not evaluated) |
| `sohee` | Female (Korean-tuned) |
| `ryan`, `aiden`, `eric`, `dylan`, `uncle_fu` | Male |

**NOT VERIFIED:** which preset is best for elderly Russian phone speech. Per `ai-model-evaluation` skill, run internal listen test (≥3 raters) before production claim.

## Voice cloning (`ref_audio`)

`mlx_audio` supports optional reference audio (not training):

```yaml
tts:
  voice: vivian          # ignored when ref_audio is set and valid
  ref_audio: assets/voice_refs/vera_ref.wav
  ref_text: "Текст, произнесённый в reference WAV"
```

Requirements for real cloning (not done in this repo yet):

1. Clean 5–15 s mono WAV, 16–24 kHz, single speaker, no music/TV
2. Matching `ref_text` transcript
3. Benchmark vs presets on phone-bandwidth fixtures (`tools/voice_lab/`)
4. ADR + license check on derived voice use

Switching preset is **not** “trained model” — only checkpoint preset or zero-shot clone from reference.
