# Investor Voice Demo — environment snapshot

**Date:** 2026-09-06  
**Machine:** MacBook Pro (Mac17,2), Apple M5, 10 cores, 16 GB RAM, integrated GPU (Metal 4)  
**OS:** Darwin 27.0.0 (arm64)  
**Repo SHA at capture:** `05855ce` + local Phase A changes (uncommitted)

## Available

| Tool | Status |
|------|--------|
| Python 3 | `/usr/local/bin/python3` |
| ffmpeg | `/opt/homebrew/bin/ffmpeg` |
| sox | `/opt/homebrew/bin/sox` |
| pytest / ruff | via `make install` |

## Not installed (blocks Phase B audio baseline)

| Dependency | Status |
|------------|--------|
| PyTorch | not installed |
| MLX | not installed |
| Ollama | not found |
| vLLM | not installed |
| faster-whisper / Qwen3-ASR | not installed |
| CosyVoice3 / Qwen3-TTS | not installed |

## Implication

Phase **B** (real STT/TTS + microphone) requires installing and benchmarking at least one STT and one TTS per ADR-003 / ADR-006. On this M5 Mac, likely paths:

1. **MLX Whisper** or **faster-whisper** (CPU/GPU) for STT baseline  
2. **Silero** (NC — demo-only) or **CosyVoice3** after model download for TTS baseline  

No cloud endpoints configured; no silent fallback will be added.

## Next install gate (suggested)

```bash
pip install faster-whisper  # or mlx-whisper on Apple Silicon
# + chosen TTS after license check
```

Record model names, versions, and first measured TTFP before claiming audio demo readiness.
