# Audio Contract — Architecture Freeze v1

> **Verified:** Silero `v5_5_ru` sample rates from [snakers4/silero-models](https://github.com/snakers4/silero-models).  
> **Spike required:** dual-leg Asterisk topology (ADR-001).

## 1. Full-duplex topology (CRITICAL)

### Rule

```text
INBOUND AUDIO  = far-end only (elder / callee)
OUTBOUND AUDIO = Vera TTS only
STT MUST NEVER receive outbound TTS as user speech
```

### Failure mode if violated

```text
Vera speaks → STT hears Vera → VAD=true → false barge-in → Vera interrupts herself
```

### Implementation (ADR-001 proposed)

```text
Caller (PJSIP)
    │
    ├── Capture leg: Snoop(inbound) → ExternalMedia IN → voice-runtime → STT
    │
    └── Inject leg:  TTS output → ExternalMedia OUT → mixing bridge → caller
```

Alternative after spike: `chan_websocket` with **separate** inbound/outbound media channels (document chosen topology in ADR-001).

References:

- [Asterisk External Media ARI](https://docs.asterisk.org/Development/Reference-Information/Asterisk-Framework-and-API-Examples/External-Media-and-ARI/)
- [chan_websocket](https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/)

### Gate: Echo self-barge-in (Phase 5 — BLOCKER)

```text
SETUP:  Vera speaks continuously 10s, elder silent

ASSERT:
  vad.user_speech == false
  stt.user_transcript == empty
  barge_in.triggered == false
  playback.state == playing_until_end
```

## 2. Sample rates and resampling

### PSTN leg

```text
Codec: PCMU (G.711 μ-law) or PCMA (G.711 A-law)
Rate:  8000 Hz
```

### Internal transport (Asterisk ↔ voice-runtime)

```text
Format: PCM signed 16-bit little-endian (slin)
Rate:   as negotiated (typically 8000 Hz on PSTN paths)
```

**Do not assume 16000 Hz on the wire.**

### STT branch

```text
Input:  inbound PCM @ transport rate
Step:   resample → 16000 Hz mono
Engine: faster-whisper large-v3-turbo (hypothesis — ADR-003)
```

Whisper family commonly uses 16 kHz internally; resampling is **our** responsibility.

### TTS branch (ADR-006 — CosyVoice3 primary candidate)

Legacy Silero v5_5_ru (ADR-002) remains a benchmark baseline, not the active production default.

```text
Primary: CosyVoice3 / ADR-006 winner @ negotiated rate → resample if needed → wire
Fallback selection: only via documented benchmark on target hardware
```

### Resampling quality

- Use dedicated resampler (e.g. soxr/libsamplerate) — not naive decimation.
- Log `source_rate`, `target_rate`, `resampler` in call trace.

## 3. TTS mode: phrase-chunked (not native streaming)

Silero public API: `model.apply_tts(text=..., speaker=..., sample_rate=...)`.

Layers (independent):

```text
1. text streaming      (LLM RendererProvider)
2. phrase chunking     (PhraseChunker — clause boundaries)
3. TTS inference       (Silero apply_tts per phrase)
4. audio delivery      (AsyncIterator[AudioChunk] to phone)
```

Silero implementation may synthesize full phrase then slice PCM into chunks for the provider contract.

## 4. Frame timing

```text
PCM16 mono frame (20 ms):
  @ 16 kHz (STT internal): 320 samples = 640 bytes
  @  8 kHz (PSTN):         160 samples = 320 bytes

pcm16_frame_bytes(16000) == 640
pcm16_frame_bytes(8000)  == 320
```

Runtime playback queue target: ~200 ms buffered audio (calibration parameter, ADR-008).

Asterisk `chan_websocket`: respect `MEDIA_WEBSOCKET_OPTIMAL_FRAME_SIZE` and `MEDIA_XOFF`/`MEDIA_XON` flow control.

## 5. Barge-in

```text
On user speech during TTS:
  1. generation_id cancel → RendererProvider.cancel() + TTSProvider.cancel()
  2. stop playback queue (<150ms p50, <250ms p95)
  3. STT continues on inbound leg only
  4. record playback accounting (phrase interrupted)
```

## 6. Playback accounting

Per `phrase_id`:

| Field | Purpose |
|-------|---------|
| `generated_text` | canonical text sent to TTS |
| `played_samples` | samples actually sent to outbound leg |
| `interrupted` | barge-in before phrase end |
| `heard_text_estimate` | optional; truncated if interrupted |

State/Renderer must not treat full instruction as heard if `interrupted=true`.

## 7. VAD

- Operates on **inbound leg only**.
- Pre-STT energy gate tuned for quiet elderly speech (calibrate in voice_lab).

## 8. Trace markers (latency)

```text
speech_end
endpoint
stt_final
planner_done
llm_first_token
phrase_commit
tts_first_pcm
playback_start
bargein_detected
playback_stopped
tts_cancelled
llm_cancelled
```
