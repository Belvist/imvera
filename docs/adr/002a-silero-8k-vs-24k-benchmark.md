# ADR-002a: Silero 8 kHz vs 24 kHz PSTN Benchmark

**Status:** proposed (run Phase 3)  
**Date:** 2026-09-06

## Context

Silero supports 8 kHz and 24 kHz. PSTN is 8 kHz. Direct 8 kHz vs 24 kHz→resample may differ in quality and latency.

## Hypothesis

Mode A (8 kHz direct) may be faster; Mode B (24 kHz) may sound better after resample.

## Benchmark protocol

1. Record 20+ phrases through real PSTN loopback (not laptop mic).
2. Mode A: `apply_tts(..., sample_rate=8000)` → inject.
3. Mode B: `apply_tts(..., sample_rate=24000)` → soxr → 8 kHz → inject.
4. Measure: first-audio latency, MOS (≥3 listeners), artifact rate.

## Gate

ADR-002 updated to **accepted** rate choice before Phase 5 SIP lab.

## Verification status

❌ Not run yet — hypothesis only.
