# ADR-002: TTS — Silero v5_5_ru Phrase-Chunked

**Status:** accepted  
**Date:** 2026-09-06

## Context

IMVERA requires Russian TTS for Вера. Product mandate: **Silero ru v5**. Latency target: first audio <1s p50 on phone.

## Decision

- Model: `v5_5_ru` from [silero-models](https://github.com/snakers4/silero-models)
- Speaker: `kseniya` (calm female; change only via new ADR)
- API: `apply_tts(text, speaker, sample_rate)` — **phrase-chunked**, not native token streaming
- Sample rate: **8000 or 24000 Hz** (not 16000 — unsupported by model)
- Provider exposes `AsyncIterator[AudioChunk]`; adapter slices phrase PCM

## Mode name

`PHRASE_CHUNKED_TTS` — four layers: text stream → phrase commit → inference → audio chunks.

## Consequences

- PhraseChunker in voice-runtime splits Renderer output on clause boundaries.
- Pronunciation normalization in TTS service (names, dates, times).
- CosyVoice / cloud TTS: future providers implement same `TTSProvider` protocol.

## References

- [silero-models README](https://github.com/snakers4/silero-models) — rates 8000/24000/48000

## Related

- [ADR-002a](002a-silero-8k-vs-24k-benchmark.md) — rate selection benchmark
