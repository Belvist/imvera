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
  → SIP_AUDIO_TRACK_AVAILABLE (optional)
  → TRACK_SUBSCRIBED (remote SIP audio)
  → TRANSPORT_READY (local vera-audio published — opening starts here)
  → RX_MEDIA_ACTIVE (first inbound frame)
  → RX_SPEECH_ACTIVE (first non-silent caller PCM)
```

`TRANSPORT_READY` must **not** wait for inbound PCM — LiveKit SIP may ring until IMVERA publishes audio.

`CallActor.on_media_ready()` is wired to `on_transport_ready` (opening), not first inbound frame.

## Redis

LiveKit expects **Redis on `localhost:6379`** before `make livekit-up`.

- Dev with `make up`: uses `imvera-cache` (already on 6379).
- Gate-only Linux host: `docker run -d --name livekit-redis -p 6379:6379 redis:7-alpine`

`make livekit-up` pulls latest images and recreates containers (`--pull always --force-recreate`).

## Quick start (Linux recommended)

```bash
cp infra/livekit/.env.example infra/livekit/.env
# Set LIVEKIT_NODE_IP on NAT hosts
make livekit-up          # prints network summary
make livekit-health      # per-component status
make livekit-setup-sip
make livekit-sip-gate
```

## macOS Docker Desktop (Zoiper lab)

`make livekit-up` generates `infra/livekit/.runtime/` with your LAN IP (`detect_media_host`):

- LiveKit Server ICE: `rtc.node_ip` + `use_external_ip: true`
- LiveKit SIP SDP: `nat_1_to_1_ip` / `media_nat_1_to_1_ip` (not Docker bridge `172.x`)
- Announced SIP port **5065** (`sip_port`) while container listens on **5060** — required for ACK/RTP

Without this, Zoiper answers but hears silence (`audio_packets: 0`, `no ACK received`).

```bash
make zoiper-livekit-info   # Zoiper → 192.168.x.x:5065, dial +15550001000
```

Linux with `network_mode: host` remains the authoritative media gate host.


## Webhooks

LiveKit → `http://127.0.0.1:9200/livekit/webhook` (signed, local API key).

## Tear down

```bash
make livekit-down
```
