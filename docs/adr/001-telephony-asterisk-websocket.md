# ADR-001: Telephony — Asterisk + ARI + Separated Media Legs

**Status:** accepted (Architecture Freeze v1)  
**Date:** 2026-09-06

## Context

IMVERA needs inbound/outbound PSTN via SIP trunk. Voice-runtime must receive **far-end audio only** for STT and send **Vera TTS only** on outbound — see [AUDIO_CONTRACT.md](../AUDIO_CONTRACT.md).

## Decision

```text
PJSIP
  → Asterisk ≥ 22.6.0
  → Stasis ARI application
  → Dual media legs:
        Capture: Snoop(inbound) / ExternalMedia IN  → voice-runtime STT
        Inject:  voice-runtime TTS → ExternalMedia OUT → caller bridge
  → Primary transport to runtime: chan_websocket (Asterisk ≥ 22.6)
  → Fallback: AudioSocket (TCP_NODELAY required)
```

Do **not** use undifferentiated single stream STT+TTS without echo gate pass.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| chan_websocket + ARI | Framing/timing in Asterisk; JSON control | Scale reports at 90+ calls; needs spike | **Primary** |
| AudioSocket | Simple; proven for AI agents | App handles timing; separate control | **Fallback** |
| RTP ExternalMedia raw | Flexible | App does RTP timing/payload | Reject V1 |
| FreeSWITCH | Strong media | Different ops stack | Defer |

## Consequences

- Phase 5 blocked until echo self-barge-in gate passes.
- ADR-001 spike document: chosen leg wiring + Asterisk version pinned in deploy.
- SIP trunk via provider (Exolve/etc.) — credentials in env only.

## References

- [External Media and ARI](https://docs.asterisk.org/Development/Reference-Information/Asterisk-Framework-and-API-Examples/External-Media-and-ARI/)
- [chan_websocket](https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/)

## Verification status

| Claim | Status |
|-------|--------|
| ExternalMedia inject + receive | ✅ Asterisk docs |
| Dual-leg pattern for AI | ⚠️ spike Phase 5 |
| chan_websocket scale | ⚠️ monitor at pilot |
