# ADR-001: Telephony — Asterisk + ARI + Separated Media Legs

**Status:** accepted (Architecture Freeze v1, amended 2026-09-06)  
**Date:** 2026-09-06

## Context

IMVERA needs inbound/outbound PSTN via SIP trunk. Voice-runtime must receive **far-end audio only** for STT and send **Vera TTS only** on outbound — see [AUDIO_CONTRACT.md](../AUDIO_CONTRACT.md).

## Decision

```text
PJSIP
  → Asterisk ≥ 22.8.0   # JSON WebSocket control format (22.8+)
  → Stasis ARI application
  → Dual media legs:
        Capture: Snoop(inbound) / ExternalMedia IN  → voice-runtime STT
        Inject:  voice-runtime TTS → ExternalMedia OUT → caller bridge
  → Primary transport to runtime: chan_websocket
  → Fallback: AudioSocket (TCP_NODELAY required)
```

Minimum **22.6.0** if JSON control is not required; **22.8.0+** when using Asterisk JSON WebSocket control messages.

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
- [chan_websocket / WebSocket](https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/)

## Verification status

| Claim | Status |
|-------|--------|
| ExternalMedia inject + receive | ✅ Asterisk docs |
| JSON control ≥ 22.8 | ✅ Asterisk docs |
| Dual-leg pattern for AI | ⚠️ spike Phase 5 |
| chan_websocket scale | ⚠️ monitor at pilot |
