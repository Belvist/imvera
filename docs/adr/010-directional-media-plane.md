# ADR-010: Directional Media Plane — Architecture Freeze

**Status:** accepted  
**Date:** 2026-09-08  
**Supersedes:** partial wiring in ADR-001 implementation (snoop direction bug)

## Context

Forensic analysis of live call `sip-93be0754bc` proved:

- STT (GigaAM) and HTTP STT service are **correct** on the audio they receive.
- Dialogue correctly waits for `UserTurn` text.
- `raw_capture` contained **Vera TTS phrases**, not isolated caller uplink — the capture path was polluted.
- Root cause: `SnoopChannel` used `spy=out` (audio **to** caller) instead of `spy=in` (audio **from** caller).
- Secondary: 2 s preroll replayed into VAD at `listen.enabled`, triggering false `speech.started` on Vera echo.

IMVERA must never again conflate bridge-mixed audio, server TTS loopback, and acoustic echo in one "capture" stream.

## Decision

### Topology (production)

```text
                    PJSIP CALLER CHANNEL
                   /                    \
        CALLER → ASTERISK            ASTERISK → CALLER
               │                           ▲
        SnoopChannel spy=in          inject / whisper=out
               │                           ▲
      CAPTURE BRIDGE (proxy)        PLAYBACK BRIDGE (proxy)
               │                           ▲
      chan_websocket capture        chan_websocket inject
               │                           ▲
      VoiceGateway AudioIngress     TTS Playback
               │
       raw_inbound (immutable)
               │
       Echo / double-talk classifier (advisory only)
               │
          Silero VAD (persistent, per-call)
               │
        UtteranceBuilder (300 ms preroll on speech_start only)
               │
            GigaAM STT
```

### Hard rules

1. **Caller PJSIP channel** is the sole source of truth for phone media.
2. Inbound capture **never** gated by TTS, `playback_active`, dialogue state, or `answer_wait`.
3. **No** bridge-mixed audio as `raw_inbound`.
4. **No** PCM flush that discards inbound on normal TTS end.
5. **Persistent VAD** — not recreated per Vera phrase.
6. **Pre-roll 250–400 ms** from inbound caller stream only; attached at confirmed `speech_start`, never bulk-fed to VAD at `listen.enabled`.
7. **Echo classifier is advisory** — reports `ECHO | USER | DOUBLE_TALK | UNKNOWN`; never deletes raw inbound.
8. **`answer_wait_timeout` only when `MediaHealth=HEALTHY`** — stalled media → `MEDIA_STALLED`, no QuestionLedger attempt consumed.
9. **PJSIP:** `direct_media=no`; NAT: `rtp_symmetric`, `force_rport`, `rewrite_contact` where applicable.
10. **Transport:** `chan_websocket` on Asterisk 22.8+; Asterisk owns framing/timing.

### Four-layer diagnostics (every call)

```text
ASTERISK_RTP_RX  →  CAPTURE_WS_RX  →  ACTOR_PCM_RX  →  STT_INPUT
```

Trace must allow locating loss at exactly one boundary.

### Per-utterance artifacts (audit mode)

- `raw_inbound.wav` — gateway capture (directional `spy=in`)
- `processed_inbound.wav` — post-resample actor ingress
- `stt_input_<utterance>.wav`
- `playback_reference.wav`

### E2E automation (next gate)

SIPp deterministic RTP scenarios A–G (see `docs/PLAN.md` Phase 5b). Zoiper remains acoustic manual gate only.

## Consequences

- **Do not** tune GigaAM, dialogue, LLM, or TTS semantics until directional media gate passes.
- ADR-001 implementation amended: `spy=in` for capture snoop.
- `IMVERA_UPLINK_PREROLL_MS` default **300** (was 2000).
- Preroll replay into VAD at `listen.enabled` **removed**.
- `MediaHealth` + pipeline counters in gateway and call actor.

## Alternatives considered

| Option | Verdict |
|--------|---------|
| Software echo gate only (status quo) | Reject — cannot distinguish bridge loopback from user |
| Single mixed WebSocket leg | Reject — violates AUDIO_CONTRACT |
| Raw RTP in Python | Reject — ADR-001 defers to chan_websocket |
| spy=out + heavier echo ML | Reject — proven to capture Vera TTS as "user" |

## Verification status

| Claim | Status |
|-------|--------|
| spy=in capture excludes server TTS on synthetic SIP | NOT VERIFIED — SIPp gate pending |
| Zero TTS in raw_inbound (no acoustic loopback) | NOT VERIFIED |
| MEDIA_STALLED does not consume QuestionLedger | CHANGED — unit test |
| 4-layer counters in trace | CHANGED — gateway + actor |

## References

- [ADR-001](./001-telephony-asterisk-websocket.md)
- [AUDIO_CONTRACT.md](../AUDIO_CONTRACT.md)
- Forensic report: `sip-93be0754bc` (2026-09-08)
- Asterisk SnoopChannel: spy=in/out, whisper=in/out
- Asterisk chan_websocket (22.6+)
- ARI `GET /channels/{id}/rtp_statistics`
