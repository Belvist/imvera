---
name: ai-model-evaluation
description: Evaluate STT, TTS, and LLM options for Russian elderly phone speech with evidence. Use before choosing or recommending any model/provider.
---

# AI Model Evaluation

## Rule

**Never write «X is better» or «Y is fast» without measured evidence on our task.**

## Required Dimensions

For every candidate (STT / TTS / LLM):

| Dimension | Record |
|-----------|--------|
| Model name + version | exact checkpoint |
| License | commercial use OK? |
| Size | params / disk / RAM |
| Hardware | CPU/GPU, batch=1 |
| Russian quality | WER/CER or MOS on **elderly phone audio** |
| Latency | TTFT, RTF, p50/p95 |
| Streaming | partial results? cancellable? |
| Cost | per minute at pilot scale |
| Failure modes | silence, accent, noise, low volume |

## STT Evaluation

Test set must include:

- elderly speakers (not only studio)
- phone bandwidth (8 kHz narrowband simulation)
- background TV/radio noise
- short backchannels («угу», «алло»)
- safety-critical words («упал», «болит», «скорая»)

Report **confidence calibration**: does high conf mean correct on our gate?

## TTS Evaluation

- Naturalness MOS (internal listen test, ≥3 raters)
- Time to first PCM byte
- Russian prosody on names, numbers, questions
- Interruptibility (barge-in clean stop)

## LLM Evaluation

- Used as **renderer assist**, not state owner
- Latency under streaming
- Instruction following for short replies
- Refusal/hallucination on medical promises

## Benchmark Protocol

1. Freeze test audio/text set (versioned in `tools/voice_lab/fixtures/`)
2. Run all candidates same hardware
3. Store results JSON + date + git SHA
4. ADR references benchmark ID

## Output Template

```text
TASK: STT | TTS | LLM
CANDIDATES: A, B, C
HARDWARE: ...
WINNER: ... (with caveats)
NOT TESTED: ...
RECOMMENDATION: adopt | reject | more data needed
```

## Forbidden

- Blog post benchmarks as sole evidence
- English-only eval for Russian product
- Choosing largest model without latency proof
