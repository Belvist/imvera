# LiveKit self-hosted telephony (ADR-012)

Self-hosted **LiveKit Server + LiveKit SIP + Redis**. No LiveKit Cloud. No managed voice APIs.

## Stack

```text
synthetic SIP client (pyVoIP)
    → livekit-sip :5060
    → livekit-server :7880
    → IMVERA participant (livekit.rtc SDK, UDP mux :7882)
    → CallActor → GigaAM / Silero / local LLM
```

IMVERA uses **low-level `livekit.rtc` only** — not LiveKit Agents framework.

## Firewall (production)

**LiveKit Server (IMVERA rtc participant):**

| Port | Protocol | Purpose |
|------|----------|---------|
| 7880 | TCP | Signaling / HTTP API (behind ingress in prod) |
| 7881 | TCP | WebRTC ICE TCP fallback |
| **7882** | **UDP** | **WebRTC media mux (IMVERA participant)** |

**LiveKit SIP (PSTN/synthetic caller):**

| Port | Protocol | Purpose |
|------|----------|---------|
| 5060 | UDP/TCP | SIP signaling |
| **10000–20000** | **UDP** | **SIP RTP (caller ↔ LiveKit SIP)** |

Do **not** confuse:

```text
10000–20000/UDP  = SIP caller audio (LiveKit SIP)
7882/UDP         = IMVERA rtc.AudioStream participant (LiveKit Server)
```

Both require `use_external_ip: true` on NAT/public hosts with correct advertised IP in SDP.

## Room privacy

`SIPDispatchRuleIndividual` may embed caller phone digits in LiveKit `room_name` (LiveKit logs).

IMVERA uses **opaque `call_id`** (`lk-<uuid>`) — never derived from phone or room name.

Application traces use `room_ref` / `participant_ref` (hashed). Full numbers only in protected storage.

## Session readiness FSM

```text
participant_joined (webhook)
  → PARTICIPANT_DETECTED
  → IMVERA_ROOM_CONNECTED (rtc connect)
  → SIP_AUDIO_TRACK_AVAILABLE
  → TRACK_SUBSCRIBED
  → MEDIA_READY (first inbound frame)
  → CallActor.on_media_ready()
```

`participant_joined` alone does **not** start answer-wait. `TRACK_TIMEOUT` if no SIP audio track within 15s.

## Quick start (Linux recommended)

```bash
cp infra/livekit/.env.example infra/livekit/.env
# Set LIVEKIT_NODE_IP on NAT hosts
make livekit-up          # prints network summary
make livekit-health      # per-component status
make livekit-setup-sip
make livekit-sip-gate
```

## Host networking

Official LiveKit SIP dev compose uses `network_mode: host`.
On **macOS Docker Desktop**, host networking is limited — use Linux for SIP gate.

## Webhooks

LiveKit → `http://127.0.0.1:9200/livekit/webhook` (signed, local API key).

## Tear down

```bash
make livekit-down
```
