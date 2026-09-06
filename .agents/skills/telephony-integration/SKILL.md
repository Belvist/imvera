---
name: telephony-integration
description: Integrate SIP, PSTN, RTP, and telephony edge for voiseup. Use for FreeSWITCH/Kamailio, trunks, dialplan, and outbound campaigns.
---

# Telephony Integration

## Transport Role (strict)

Telephony edge **only**:

```text
SIP signaling (invite, bye, dtmf)
RTP media bridge
Codec negotiation (prefer PCMU/PCMA or opus → internal PCM16 16kHz)
NAT traversal
Inbound DID routing
Outbound gateway dial
```

Telephony edge **never**:

```text
❌ chooses dialogue replies
❌ calls LLM
❌ sets call verdict
❌ runs slot FSM
```

## Recommended Stack (pilot)

Evaluate in ADR-001:

| Component | Option |
|-----------|--------|
| Media/SIP | FreeSWITCH |
| SIP proxy | Kamailio (optional, scale later) |
| Trunk | Exolve / local carrier SIP |
| Lab client | Zoiper / Linphone |

## Audio Contract (internal)

```text
PCM16, mono, 16 kHz, 20 ms frames (320 bytes)
```

Wrong format → `media_unhealthy` event, not silent resample guess.

## Call Flow (outbound IMVERA)

```text
Scheduler (Core) → originate API
  → Telephony edge dials PSTN
  → answer → bridge to VoiceRuntime media adapter
  → CallSession.start()
  → ... dialogue ...
  → hangup → CallEvents to Core
```

## Call Flow (inbound)

```text
PSTN → DID → dialplan → park/bridge → VoiceRuntime
```

Dialplan = routing only. One line to hand off call_id to runtime.

## DTMF

Use for: consent confirm, «перезвоните позже», menu escape.
Map to explicit events — not raw string in dialogue brain.

## Observability

Per call:

```text
call_id, sip_call_id, trunk, codec, mos (if available)
recording_uri, start_ts, end_ts, hangup_cause
```

## Gates

| Gate | Proof |
|------|-------|
| Lab SIP | Zoiper ↔ local FS ↔ VoiceRuntime, recording exists |
| Outbound | test number rings, two-way audio |
| PSTN | real mobile answers, trace complete |
| Failover | trunk down → TECHNICAL event, not GREEN |

## Security

- SIP creds in vault/env
- ACL on originate API
- Rate limit outbound per household

## Forbidden

- Lua/Python in dialplan as dialogue brain
- ESL open to 0.0.0.0
- Assuming 8 kHz PSTN without explicit resample module
