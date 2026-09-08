# ADR-011: Telephony Adapter — Telnyx Media Streaming

**Status:** **rejected** (superseded by [ADR-012](012-self-hosted-telephony-livekit.md))  
**Date:** 2026-09-08  
**Rejected:** 2026-09-08

## Why rejected

IMVERA requires the **full voice stack on our servers**. Telnyx is a managed programmable voice API — media and call control would cross an external boundary. This violates project policy:

> No Twilio, Telnyx, Deepgram, ElevenLabs, LiveKit Cloud, or similar external voice/AI APIs.

Production telephony is **LiveKit SIP + LiveKit Server (self-hosted)** per ADR-012. SIP trunk operator is the only external hop (SIP/RTP only).

## What remains in repo (experimental, not production)

Spike code kept for reference only — parser, codec reorder patterns:

```text
packages/telephony/telnyx*.py
services/voice_gateway/telnyx_media.py   # /telnyx/media — do not deploy
scripts/telnyx_media_gate.py
tests/test_telnyx_*.py
```

Do **not** wire live Telnyx credentials, purchase numbers, or treat `make telnyx-media-gate` as a production gate.

## Original context (archived)

Forensic Asterisk uplink failure motivated leaving custom snoop/bridge. Telnyx was evaluated as industry pattern (carrier → bidirectional media WebSocket). Correct direction for IMVERA is self-hosted LiveKit track model, not managed carrier streaming.

See ADR-012 for accepted decision.
