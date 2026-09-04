# Realtime Streaming Hot Path

> **Status (Wave RT-1):** `STREAMING_INGRESS_PROVEN` when
> `python3 scripts/prove_streaming_ingress.py` exits 0.
> This is **not** `STREAMING_COMPLETE` — playback/TTS/barge-in follow in RT-3/RT-4.

## Goal

Вера начинает ответ **почти сразу** после того, как пользователь закончил мысль,
и **мгновенно замолкает** при перебивании.

Не оптимизировать legacy WAV/HTTP pipeline как конечную архитектуру.
Legacy остаётся fallback (`LEGACY_FALLBACK=1`).

## Not production target

```
record WAV → full STT → HTTP turn → seg WAV → file polling → playback
```

Допустимы дешёвые улучшения на legacy, но **не** строить дальнейшую архитектуру вокруг этого.

## Canonical target

```
continuous PCM
  → VAD (speech / silence only)
  → TurnDetector.is_complete()
  → streaming/fast STT (incremental input)
  → Golden Path Planner
  → LLM SSE (stream=true)
  → TextChunker
  → TTSWorker (chunked PCM)
  → PCM ring buffer
  → continuous playback
  → barge-in cancels generation_id
  → Actual Heard ledger
```

## Environment flags

| Variable | Default | Meaning |
|----------|---------|---------|
| `VERA_GOLDEN_PATH` | `0` | Use Golden Path brain on realtime path |
| `LEGACY_FALLBACK` | `1` | Keep legacy conversation_system for phone |
| `MOSS_ENDPOINT_SILENCE_MS` | `700` | Tuned endpoint silence (elderly-safe) |
| `MOSS_ENDPOINT_MIN_SPEECH_MS` | `220` | Minimum speech before endpoint |
| `MOSS_VOICE_GATEWAY_PORT` | `9720` | WebSocket PCM ingress |
| `MOSS_PCM_CACHE_DIR` | `voice_runtime/pcm_cache_store` | Deterministic control PCM |

## Tracks

### Track A — Cheap latency wins (parallel, not substitute)

- **A1** `voice_runtime/pcm_cache.py` — deterministic PCM for WAIT/CLOSE/…
- **A2** `voice_runtime/text_chunker.py` — LLM SSE → speakable chunks (15–30 / 30–70 chars)
- **A3** LLM SSE barrier test — consumer gets chunk 1 before chunk 2 (`telephony/tests/test_providers.py`)

### Track B — Continuous audio ingress (main ROI)

- **B1** `VoiceGatewayServer` + `GatewayIngressSession` — `call_id`, `audio_sequence`, timestamps
- **B2** Silero/RMS VAD — speech started / active / silence only
- **B3** `TurnDetector.is_complete()` — Smart Turn plugs in later

FreeSWITCH: `mod_audio_fork` → `ws://127.0.0.1:9720/stream` (mono int16 LE @ 16 kHz).
8 kHz telephony PCM → resample once to 16 kHz (`voice_runtime/media_tap.resample_linear`).

### Track C — STT

Interface (Wave RT-2+):

```
start_stream() → push_pcm(frame) → partial() → finalize()
```

Metrics: `stt_first_partial_ms`, `stt_final_ms`.

### Track D — Golden Path in realtime

`golden_path/realtime_adapter.py`:

```
RealtimeTurn → GoldenPathEngine.handle_turn()
```

**Do not** extend legacy `conversation_system` FSM for realtime.

### Track E — LLM streaming

`POST /v1/chat/completions` with `stream=true` → `StreamTextChunker`.

### Track F — TTS streaming interface

```
TTSWorker.start(generation_id)
TTSWorker.push_text(segment)
TTSWorker.audio_chunks()  # raw PCM frames
TTSWorker.cancel(generation_id)
```

Pipeline streaming first; true-streaming Qwen TTS swaps inside `TTSWorker` later.

### Track G — PCM ring buffer

100–250 ms playback buffer; start play at safe minimum; track `buffer_underflow`.

### Track H — Barge-in (required)

On verified user speech during Vera playback:

1. Stop playback
2. Invalidate `generation_id`
3. Abort LLM SSE
4. Cancel TTS
5. Clear ring buffer
6. Mark segments `CANCELLED`
7. Resume user capture

Target: p95 ≤ 250 ms to silence.

### Track I — Actual Heard

Segment lifecycle: `GENERATED → SYNTHESIZED → QUEUED → PLAYING → PLAYED | CANCELLED`.
Question is **HEARD** only when audio segment `PLAYED`.

### Track J — End-to-end latency trace

`voice_runtime/ingress_trace.py` — per-turn timestamps and derived metrics:

- `endpoint_latency`, `stt_final`, `llm_ttft`, `tts_first_pcm`
- `speech_end_to_first_audio`, `barge_in_stop_latency`

## Latency targets

| Metric | First goal | After stabilization |
|--------|------------|-------------------|
| speech end → first Vera audio | p50 ≤ 800 ms, p95 ≤ 1200 ms | p50 ~400–600 ms |
| barge-in stop | p95 ≤ 250 ms | — |

Elderly UX: prefer ~600 ms **correct** endpoint over 250 ms with false cuts.

## Implementation waves

| Wave | Scope | Gate |
|------|-------|------|
| **RT-1** | Latency trace, PCM cache scaffold, TextChunker, LLM SSE verify, **continuous ingress proof** | PCM frames during speech (not post-record) |
| **RT-2** | VoiceGateway session, continuous VAD, incremental STT, Golden adapter, endpoint | `speech_end` → committed text without WAV cycle |
| **RT-3** | LLM SSE → TextChunker → TTS PCM → ring buffer → playback | No disk WAV between TTS and play |
| **RT-4** | Full barge-in, Actual Heard, generation lifecycle | Cancel ≤ 250 ms p95 |
| **RT-5** | Smart Turn, speculative gen, true-streaming Qwen TTS | — |

## Proof (RT-1)

```bash
# Offline synthetic utterance (CI-safe)
python3 scripts/prove_streaming_ingress.py

# Optional WebSocket path
python3 scripts/prove_streaming_ingress.py --ws --port 9721

# Unit tests
python3 -m unittest voice_runtime.test_streaming_ingress -v
```

Success: stderr prints `STREAMING_INGRESS_PROVEN` and JSON shows
`frames_during_speech >= 3` with `last_pcm_before_end_ms` set.

## Do not

- New Lua architecture for streaming
- File polling as primary transport
- More legacy conversation FSM / pools on realtime path
- Wait for perfect Qwen streaming TTS before pipeline streaming
- Speculative LLM before measurable baseline

## Related docs

- [`VOICE_GATEWAY.md`](VOICE_GATEWAY.md) — WebSocket integration
- [`STT_STREAMING_SPIKE.md`](STT_STREAMING_SPIKE.md) — STT interface spike
- [`GOLDEN_PATH.md`](GOLDEN_PATH.md) — text brain (Stage A)
