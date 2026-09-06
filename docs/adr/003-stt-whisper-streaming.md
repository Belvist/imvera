# ADR-003: STT — IMVERA Voice Benchmark (Qwen3-ASR vs Whisper)

**Status:** accepted (supersedes faster-whisper-only hypothesis)  
**Date:** 2026-09-06

## Context

Elderly Russian speech over PSTN 8 kHz — studio WER does not predict field safety recall.  
ADR-003 originally hypothesized faster-whisper `large-v3-turbo` only; Phase 3 requires evidence-based selection.

## Decision

Run **IMVERA STT Benchmark** before picking production STT:

| Candidate | Role |
|-----------|------|
| **Qwen3-ASR-0.6B** streaming (vLLM) | Primary latency candidate |
| **Qwen3-ASR-1.7B** streaming (vLLM) | Primary accuracy candidate |
| **Whisper large-v3-turbo** (faster-whisper) | Control baseline |

### Input contract

```text
PSTN inbound PCMU/PCMA 8 kHz
  → resample to 16 kHz mono PCM
  → STT provider
```

Qwen3-ASR official streaming path: vLLM, PCM 16 kHz ([Qwen3-ASR model cards](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)).

### Primary metrics (not WER alone)

```text
CRITICAL PHRASE RECALL @ acceptable latency
  "упала" / "упал"
  "не могу встать"
  "помогите"
  "голова кружится"
  "мне плохо"
  "скорая"
```

Secondary: end-of-speech → partial/final latency p50/p95, degradation under TV/noise/speakerphone.

### Winner criteria

Primary STT = best **critical phrase recall** on IMVERA corpus **and** meets realtime SLO (p50 <1s to usable partial on phone path), unless safety recall gap is unacceptable.

No silent fallback — explicit ADR required for any provider change.

## asr_quality (unchanged)

Wrapper maps logprobs, no_speech, critical terms, RMS → `GOOD | LOW | UNUSABLE`.  
`LOW` on safety-critical terms → clarify, never guess.

## Consequences

- Phase 3A: STT lab implements all three behind `STTProvider`
- ADR amended when benchmark winner recorded with corpus version + scores
- faster-whisper remains valid **control**, not default production choice

## Verification status

❌ Benchmark not run yet — blocked on Phase 3A lab setup.
