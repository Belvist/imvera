# ADR-012: Self-Hosted Telephony Media Plane (LiveKit + LiveKit SIP)

**Status:** accepted  
**Date:** 2026-09-08  
**Supersedes:** [ADR-011](011-telephony-adapter-telnyx.md) (rejected)

## Context

IMVERA voice stack must run **entirely on our infrastructure**. No managed voice APIs for STT, TTS, LLM, or realtime media transport.

**Hard rule:**

> The full voice stack runs on our servers. No Twilio, Telnyx, Deepgram, ElevenLabs, LiveKit Cloud, or similar external voice/AI APIs.

The only external dependency for ordinary phone numbers is a **SIP trunk operator** that delivers PSTN as SIP/RTP to our edge. After the SIP boundary, call audio, dialogue, and AI stay on our hardware.

ADR-011 proposed Telnyx Media Streaming as production path. That violates the self-hosted rule: media and call control would leave our boundary. **ADR-011 is rejected.**

Forensic evidence from Asterisk lab (ADR-010) remains valid:

| Finding | Implication |
|---------|-------------|
| GigaAM, dialogue, TTS work | Runtime brain is not the blocker |
| Asterisk `SnoopChannel` + bridge + ExternalMedia uplink broken | Custom Asterisk media glue is not production path |
| `spy=in/out`, whisper, capture bridge | **Eliminate** — wrong abstraction for AI voice |

We need a telephony layer that exposes **directional audio tracks**, not PBX channel snoop semantics.

## Decision

### Production telephony (pilot → prod)

```text
                    OUR SERVERS
┌────────────────────────────────────────────────────┐
│  SIP trunk (operator — SIP/RTP only)               │
│      ↓                                             │
│  LiveKit SIP          (self-hosted)                  │
│      ↓                                             │
│  LiveKit Server       (self-hosted)                  │
│      ↓                                             │
│  caller audio track  →  IMVERA CallActor            │
│      ↓                    Silero VAD (local)         │
│                           GigaAM STT (local GPU)    │
│                           LLM (local vLLM)          │
│                           Silero TTS (local)        │
│  Vera audio track    ←  playback                    │
│      ↓                                             │
│  LiveKit SIP → SIP trunk → phone                    │
└────────────────────────────────────────────────────┘
```

**Session model:**

```text
SIP caller → Participant → AudioTrack (inbound)
IMVERA TTS → AudioTrack (outbound)
```

No `SnoopChannel`, `spy=in/out`, `ExternalMedia`, or capture bridge in production.

### Full stack (self-hosted)

| Layer | Component |
|-------|-----------|
| Phone numbers | SIP trunk operator (SIP/RTP handoff only) |
| SIP/RTP gateway | **LiveKit SIP** (self-hosted) |
| Realtime media | **LiveKit Server** (self-hosted) |
| State | Redis (self-hosted) |
| Voice runtime | `CallActor` / `TurnManager` (unchanged contracts) |
| VAD | Silero VAD (local) |
| STT | GigaAM v3 RNNT (local GPU) |
| LLM | Local model via vLLM |
| TTS | Silero (local GPU/CPU) |
| DB | PostgreSQL (local) |
| Observability | Prometheus + Grafana + Loki/OTel (local) |
| Asterisk | **Lab / reference only** |

### Directional media invariant (ADR-010 extended)

```text
caller audio track  ──→ STT pipeline
Vera audio track    ──→ caller earpiece
```

When Vera speaks, her **server-side outbound track** must not appear on the **caller inbound track**. If it does, that is real acoustic echo (speaker → mic → SIP), not bridge wiring — and we handle it with echo-ref / barge-in policy, not snoop direction hacks.

`canonical_assistant_text == phone_spoken_text` — transport never rewrites Vera's words.

### Lab / reference

- Asterisk + Zoiper + `chan_websocket` — regression and comparative forensics only.
- Telnyx spike code (`packages/telephony/telnyx_*`, `/telnyx/media`) — **experimental, not production**; kept for parser/reorder reference only.

### Rejected

| Option | Verdict |
|--------|---------|
| Telnyx Media Streaming | **Reject** — managed voice API; ADR-011 superseded |
| Twilio Media Streams | **Reject** — managed voice API |
| Deepgram / ElevenLabs / OpenAI voice APIs | **Reject** — external AI/voice |
| Yandex SpeechKit / cloud STT-TTS | **Reject** — external AI |
| LiveKit Cloud | **Reject** — managed realtime; self-hosted LiveKit only |
| Asterisk snoop/bridge as production uplink | **Reject** — proven broken in lab |
| FreeSWITCH as primary AI glue | **Defer** — mature PBX, but same channel/RTP/ESL glue problem; LiveKit track model is cleaner for AI runtime |

### Why LiveKit SIP over FreeSWITCH (for IMVERA)

FreeSWITCH is mature for telephony media (RTP through server, ESL, diagnostics). But the integration model remains SIP channel → RTP leg → application glue.

LiveKit SIP maps:

```text
SIP caller → Participant → AudioTrack
```

This aligns with `CallActor` ingress/egress without assembling bridges manually.

## Infrastructure (minimum)

```text
livekit-server
livekit-sip
redis

imvera-voice-runtime
imvera-stt-gigaam
imvera-tts-silero
imvera-llm-vllm

postgres
prometheus
grafana
```

**Network (LiveKit SIP self-hosted):**

- SIP `5060` (and TLS if used) exposed to trunk
- RTP UDP range (default `10000–20000`) with correct **advertised external IP**
- All AI services on private network; no outbound voice API calls

**Without external SIP provider:** GSM/E1/PRI gateway or direct operator SIP peering to our `livekit-sip` — still operator at physical layer, no cloud voice APIs.

## Package layout (target)

```text
packages/telephony/
  livekit/           # LiveKit room participant adapter (NEW)
  adapter.py         # TelephonyAdapter contract (existing)
  asterisk.py        # lab only
  experimental/      # telnyx spike (not production)

services/
  voice_gateway/     # CallActor wiring
  livekit_agent/     # optional: LiveKit agent worker entry (phase 2)

docker/
  livekit/           # livekit-server + livekit-sip compose (NEW)
```

## Consequences

- Stop all Telnyx production work; do not purchase numbers or wire live Telnyx gate.
- Next implementation slice: Docker `livekit-server` + `livekit-sip` → IMVERA as room participant → synthetic SIP call → inbound track → GigaAM → outbound track. **Do not patch Asterisk snoop for production.**
- `TelephonyAdapter` contract remains; LiveKit implementation replaces Telnyx/Asterisk production paths.
- Comparative gate (when both paths exist): lost turns, wrong-direction audio, stalls, ingress→`stt.final` latency.

## Verification status

| Claim | Status |
|-------|--------|
| `infra/livekit` docker-compose + configs | CHANGED |
| `LiveKitCallSession` + outbound pump + supervisor | CHANGED |
| `POST /livekit/webhook` signed webhooks | CHANGED |
| `/telnyx/media` disabled by default | CHANGED |
| Unit gate `make livekit-sip-gate` (11 tests) | VERIFIED — no Docker required |
| Synthetic SIP → GigaAM «хорошо» live gate | NOT VERIFIED — needs `make livekit-up` on Linux |
| Barge-in `clear_queue` live duplex | NOT VERIFIED |

## References

- [LiveKit SIP server (self-hosted)](https://docs.livekit.io/transport/self-hosting/sip-server/)
- [LiveKit self-hosting overview](https://docs.livekit.io/transport/self-hosting/)
- ADR-010 directional media plane
- ADR-001 Asterisk lab topology (reference only)
- ADR-011 Telnyx (rejected)
