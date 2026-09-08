# ADR-013: Production Telephony — FreeSWITCH + PCM WebSocket Bridge

**Status:** accepted  
**Date:** 2026-09-08  
**Supersedes:** [ADR-012](012-self-hosted-telephony-livekit.md) (production path)  
**Amends:** [ADR-001](001-telephony-asterisk-websocket.md) (Asterisk → lab/archive only)

## Context

IMVERA needs a telephony edge that **answers calls reliably** and exposes **directional PCM** to `CallActor` without room/participant/webhook/readiness FSM complexity.

Forensic evidence (2026-09):

| Finding | Implication |
|---------|-------------|
| GigaAM, Silero VAD/TTS, dialogue, CallActor work on clean PCM | AI stack is not the first blocker |
| Asterisk `SnoopChannel` / ExternalMedia uplink broken in lab | Asterisk is **lab/archive**, not production glue |
| LiveKit SIP path: dispatch → room → participant → track → subscription → AudioStream | Too many states for «answer + hear audio» |
| `MEDIA_READY = first inbound frame` created answer deadlock with LiveKit SIP | Readiness model fought telephony semantics |
| Mac Docker NAT / host networking unreliable for LiveKit SIP RTP | Lab useful for unit code; **not** production proof |

LiveKit remains valuable as a **spike and comparative lab** (directional track model, gate scripts, readiness lessons). It is **rejected for production telephony** because we used it at the wrong abstraction layer for a plain phone AI system.

Self-hosted rule from ADR-012 **unchanged**: no Twilio, Telnyx, Deepgram, ElevenLabs, LiveKit Cloud, or managed voice APIs. SIP trunk operator at PSTN boundary only.

## Decision

### Production telephony (pilot → prod)

```text
Phone / SIP trunk operator
        ↓
    FreeSWITCH (mod_sofia)
        ↓ SIP/RTP — FS answers, not AI
   PCM media bridge (WebSocket)
        ↓
 imvera-media-bridge / voice_gateway
        ↓
     CallActor
 ├─ Silero VAD      (local)
 ├─ GigaAM v3 RNNT  (local GPU)
 ├─ local LLM       (vLLM)
 └─ Silero TTS      (local)
        ↓
   PCM write-back
        ↓
    FreeSWITCH → phone
```

**PCM bridge dependency (explicit — no silent lock-in):**

| Phase | Path |
|-------|------|
| P0 validation | `mod_audio_stream` — prove FS answer + PCM |
| Production | **Choose A or B before pilot** — no silent fallback |

- **A)** Licensed bidirectional `mod_audio_stream` (commercial v1.0.3+; free tier ≤10 concurrent channels per upstream README)
- **B)** Custom `mod_imvera_audio` on FreeSWITCH media-bug API

Community edition is primarily **uplink streaming**; do not assume free bidirectional playback as eternal production dependency. See `infra/freeswitch/MOD_AUDIO_STREAM.md` for pinned upstream + edition boundary.

**Integration path (phase 1 — P0 only):** FreeSWITCH + `mod_audio_stream` for transport proof.

**Integration path (production):** A or B above — decided before GigaAM on phone path.

```text
READ leg:  caller PCM → WS → IMVERA
WRITE leg: IMVERA PCM → WS → caller
```

### Hard rules (non-negotiable)

1. **FreeSWITCH answers the call** — not webhook, not CallActor, not first PCM frame.

```text
INVITE → FreeSWITCH answer → 200 OK → RTP established → IMVERA attaches to media
```

If IMVERA/STT/LLM unavailable:

```text
FreeSWITCH → play local «сервис временно недоступен» → hangup
```

Never: 30s silence while waiting for AI.

2. **Directional media only** — no `both`, `mixed`, `snoop`, or room audio for STT.

```text
raw_inbound.wav = caller READ leg only
```

Vera on inbound = real acoustic echo at phone, not server-side routing.

3. **Transport never generates Vera speech** — `canonical_assistant_text == phone_spoken_text`.

4. **AI stack frozen** — only telephony adapter changes:

| Component | Status |
|-----------|--------|
| Silero VAD | keep |
| GigaAM v3 RNNT | keep |
| CallActor / TurnManager | keep |
| Dialogue / Planner / State | keep |
| local LLM | keep |
| Silero TTS | keep |

### Rejected for production telephony

| Option | Verdict |
|--------|---------|
| LiveKit SIP (self-hosted) | **Reject production** — superseded by this ADR; keep `infra/livekit` as lab/spike |
| LiveKit Cloud | **Reject** |
| Asterisk snoop/bridge/ExternalMedia | **Reject production** — lab/archive |
| Telnyx / Twilio media | **Reject** — ADR-011 |
| Kamailio + RTPengine now | **Defer** — carrier scale later |

### Lab / archive

| Path | Role |
|------|------|
| `archive/telephony/livekit/` | Spike, unit gates — **not production** |
| `docker/asterisk/`, `packages/telephony/asterisk.py` | Forensics / comparative lab |
| `packages/telephony/telnyx_*` | Experimental parser reference |

### Scale path (later — not now)

```text
Kamailio / OpenSIPS → SIP routing
        ↓
FreeSWITCH workers (FS1, FS2, …)
        ↓
IMVERA runtime
```

Add RTPengine when multi-node media relay is required. **Out of scope** for first production slice.

## P0 gates (before GigaAM on phone)

Two **independent** gates — do not mix telephony proof with AI duplex bridge.

### P0-A — FreeSWITCH telephony core (current)

Community `mod_audio_stream` = **uplink READ only**. Outbound 880 Hz = **FreeSWITCH `tone_stream`** (not bridge WS).

| # | Criterion |
|---|-----------|
| 1 | INVITE → 200 OK (FS answers) |
| 2 | 440 Hz reaches bridge → `raw_inbound.wav` |
| 3 | Caller hears 880 Hz (FS `tone_stream`) |
| 4 | 880 Hz **absent** from `raw_inbound.wav` |
| 5 | Hangup cleanup; second call without restart |
| 6 | Soak **100/100** |

After P0-A 100/100 → **freeze FreeSWITCH telephony core**.

### P0-B — duplex bridge (after P0-A)

Custom `mod_imvera_audio` (preferred). **Do not** build production on commercial bidirectional `mod_audio_stream`.

| # | Criterion |
|---|-----------|
| 1 | FS READ → WS → IMVERA |
| 2 | IMVERA → WS → FS WRITE |
| 3 | Same directional 440/880 invariants |
| 4 | Then wire CallActor (no STT in module) |

Trace stages (P0-A):

```text
fs.invite → fs.answer → bridge.ws.connected
bridge.read.first_frame (440 Hz)
fs.tone_stream.880 (caller downlink)
fs.hangup → bridge.session.closed
```

## Package layout (target)

```text
packages/telephony/
  adapter.py
  freeswitch_bridge.py
  ws_protocol.py          # browser lab only

tools/telephony_gate/     # 440/880 tone + evidence (neutral)

infra/freeswitch/

services/
  imvera_media_bridge/    # PCM WS (transport P0)
  voice_gateway/          # CallActor (browser lab + future FS wiring)

lab/asterisk/             # forensic lab

archive/telephony/
  livekit/
  telnyx/
```

## Consequences

- **Stop** LiveKit production work and Linux `livekit-media-gate` as acceptance gate for pilot.
- **Keep** LiveKit unit tests and readiness refactor as regression reference; do not delete without ADR.
- **Start** vertical slice: FS docker + mod_audio_stream + `imvera-media-bridge` + 880/440 gate.
- `TelephonyAdapter` contract unchanged; FreeSWITCH bridge is new production implementation.
- Diagnostics: `fs_cli` — `show channels`, `show calls`, `sofia status` — telephony-layer truth before blaming STT.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| FreeSWITCH + mod_audio_stream | Mature SIP; FS answers; bidirectional WS; carrier diagnostics | Extra module (not FS core) | **Production P0** |
| Custom mod_imvera_audio | Full control, minimal deps | C module maintenance | Phase 2 if needed |
| LiveKit SIP | Clean track model | Room/webhook FSM; SIP answer coupling; ops on Mac lab | **Reject prod** |
| Asterisk ARI + chan_websocket | In-repo lab | Snoop uplink broken | **Lab only** |
| Kamailio + RTPengine + FS | Carrier scale | Overkill for 1-server pilot | **Defer** |

## Verification status

| Claim | Status |
|-------|--------|
| ADR-013 accepted | CHANGED |
| FreeSWITCH infra + bridge | NOT VERIFIED |
| P0 880/440 gate 100/100 | NOT VERIFIED |
| GigaAM on FS path | NOT VERIFIED — blocked on P0 |

## References

- [FreeSWITCH SIP profiles (Sofia)](https://developer.signalwire.com/freeswitch/users-and-endpoints/sip-profiles/)
- [FreeSWITCH diagnostic toolbox](https://developer.signalwire.com/freeswitch/troubleshooting/toolbox/)
- [mod_audio_stream](https://github.com/amigniter/mod_audio_stream)
- ADR-010 directional media plane
- ADR-012 LiveKit (superseded for production)
