# ADR-003: STT — faster-whisper large-v3-turbo + Streaming Wrapper

**Status:** proposed (hypothesis until PSTN benchmark)  
**Date:** 2026-09-06

## Context

Elderly Russian speech over PSTN 8 kHz — studio WER benchmarks do not apply.

## Decision (hypothesis)

- Engine: faster-whisper `large-v3-turbo` (CTranslate2)
- Input: inbound PCM resampled to **16 kHz mono**
- Streaming: wrapper (sliding window / partial finals) — **not native** to faster-whisper
- Output contract: `STTResult` with `asr_quality` (our function), not raw confidence threshold

## asr_quality factors

```text
avg_logprob, no_speech_prob, critical_terms match,
audio_quality.rms, phrase length sanity
→ GOOD | LOW | UNUSABLE
```

`LOW` on safety-critical terms → clarify question, never guess.

## Gate

`IMVERA Voice Benchmark` corpus (Phase 3/7): critical phrase recall for упал/помогите/болит/скорая.

## Alternatives if gate fails

- smaller/faster model for latency
- cloud STT with explicit ADR (no silent fallback)
- distil-whisper variants

## Verification status

❌ Russian elderly PSTN not benchmarked yet.
