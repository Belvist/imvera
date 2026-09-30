# ADR-006: TTS Benchmark — CosyVoice3 vs Qwen3-TTS (Silero reference only)

**Status:** accepted  
**Date:** 2026-09-06  
**Supersedes:** [ADR-002](superseded/002-tts-silero-v5-phrase-chunked.md) for production choice

## Context

IMVERA needs Russian phone TTS for Вера: natural prosody, names/dates, cancellable streaming, commercial license.  
Silero `v5_5_ru` is NC-licensed — see ADR-002 supersede note.

## Decision

Run **IMVERA TTS Benchmark** on phone channel (8 kHz output path):

| Candidate | License | Notes |
|-----------|---------|-------|
| **Fun-CosyVoice3-0.5B-2512** | Apache-2.0 | Primary candidate; Russian; streaming |
| **Qwen3-TTS** (0.6B / 1.7B per lab capacity) | Apache-2.0 | Second candidate; streaming via vLLM-Omni |
| **Silero v5_5_ru** (`kseniya`) | CC BY-NC-SA | Reference only unless commercial license obtained |

### Architecture (unchanged)

```text
Renderer text → phrase commit → TTSProvider.synthesize()
  → AsyncIterator[AudioChunk] + generation_id + cancel()
```

Phrase-chunked delivery remains valid even for natively streaming models.

### Metrics

```text
TTFP (time to first phone audio) p50 / p95
Cancellation stop latency p50 / p95
Russian elderly phone intelligibility (human eval)
Names, dates, times, digits
Stress / calm delivery (Вера persona)
```

### Winner

Production TTS = benchmark winner on **phone 8 kHz** path meeting latency SLO + human quality gate.

## Consequences

- Phase 3B: TTS lab; no production TTS until benchmark recorded
- Silero ADR-002a rate benchmark deferred unless Silero re-licensed

## References

- [Fun-CosyVoice3-0.5B-2512](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512)
- [silero-models LICENSE](https://github.com/snakers4/silero-models)

## Verification status

❌ Benchmark not run yet.
