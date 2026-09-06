# ADR-002: TTS — Silero v5_5_ru Phrase-Chunked

**Status:** superseded by [ADR-006](006-tts-benchmark-cosyvoice-qwen.md)  
**Date:** 2026-09-06

## Context

IMVERA requires Russian TTS for Вера. Initial mandate referenced Silero `v5_5_ru`.

## Decision (historical)

- Model: `v5_5_ru` from [silero-models](https://github.com/snakers4/silero-models)
- Speaker: `kseniya`
- API: `apply_tts()` — phrase-chunked
- Sample rate: **8000 or 24000 Hz**

## Why superseded (2026-09-06)

Official [silero-models LICENSE](https://github.com/snakers4/silero-models) is **CC BY-NC-SA 4.0** for models including `v5_5_ru`.  
**Non-commercial** — not acceptable for commercial IMVERA production without a separate commercial license from Silero.

Silero may remain:

- reference / internal R&D benchmark only (if license permits evaluation)
- production candidate **only after** explicit commercial license

Architecture unchanged: `TTSProvider` + phrase-chunked `AsyncIterator[AudioChunk]` + `cancel()`.

## Related

- [ADR-006](006-tts-benchmark-cosyvoice-qwen.md) — production TTS benchmark
- [ADR-002a](002a-silero-8k-vs-24k-benchmark.md) — rate selection (if Silero re-licensed)
