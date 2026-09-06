---
name: performance-realtime
description: Design and measure realtime voice latency, streaming, and barge-in for voiseup. Use for hot path changes and provider selection.
---

# Performance & Realtime

## Hot Path Definition

```text
speech_end → endpoint → stt_final → planner_done →
llm_first_token → text_commit → tts_first_pcm → playback_start
```

**Nothing synchronous from Postgres/S3/HTTP-to-Core in this path.**

Async after `text_commit` or after hangup: persistence, analytics, Core events.

## Trace Events (mandatory)

Every turn log:

```text
speech_end
endpoint
stt_final
planner_done
llm_first_token      # if LLM used
text_commit          # canonical text frozen
tts_first_pcm
playback_start
bargein_detected     # if applicable
playback_stopped
tts_cancelled
llm_cancelled
generation_id
```

## Barge-in Contract

1. User speech during playback → `bargein_detected`
2. Stop playback within 200 ms target
3. Cancel in-flight TTS/LLM with matching `generation_id`
4. Drop stale PCM frames (generation mismatch)
5. Never play audio from cancelled generation

## Streaming Strategy

| Stage | Prefer |
|-------|--------|
| STT | partial → final |
| LLM | token stream to renderer (if used) |
| TTS | chunk PCM as soon as clause ready |
| Playback | queue 20 ms frames; don't wait for full WAV |

## Measurement

- `tools/voice_lab/latency_baseline.py` (when implemented)
- Report p50, p95 per segment
- Hardware note: CPU vs GPU, RAM, model size

## Targets (pilot)

See `PROJECT_CONTEXT.md` latency table.

## Forbidden

- Blocking on full sentence TTS before any playback (unless ADR)
- Ignoring barge-in to «finish the phrase»
- Measuring only mean without p95
