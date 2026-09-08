# Current task — LiveKit PRE-LIVE ACCEPT (gate split)

**Outcome:** Freeze transport architecture. Prove caller audio reaches IMVERA PCM **before** AI stack.

## Architecture freeze

No new telephony architecture changes until Linux media-gate PASS.

## Gates

| Gate | Command | Requires |
|------|---------|----------|
| Transport | `make livekit-media-gate` | redis, livekit, SIP, gateway with `IMVERA_LIVEKIT_MEDIA_GATE=1` |
| AI | `make livekit-sip-gate` | media-gate stamp + Silero/GigaAM/LLM/TTS |

## Linux sequence

```bash
export LIVEKIT_NODE_IP=<PUBLIC_IP>
make livekit-up
make livekit-health          # --mode media (default)
make livekit-setup-sip

# voice gateway with IMVERA_LIVEKIT_MEDIA_GATE=1
IMVERA_LIVEKIT_GATE_REQUIRE_STACK=1 make livekit-media-gate
# STOP if FAIL

# start inference stack, gateway without media_gate-only if needed
IMVERA_LIVEKIT_GATE_REQUIRE_STACK=1 make livekit-sip-gate
```

## Privacy (production blocker)

`dispatchRuleIndividual` embeds caller digits in LiveKit `room_name` (LiveKit internal logs — no PII redaction). OK for synthetic gate; **must** move to opaque room routing before PSTN.

## NOT VERIFIED

- Live media-gate on Linux host (needs `IMVERA_LIVEKIT_GATE_REQUIRE_STACK=1`)
- 10/100 deterministic call soak
- Real SIP trunk operator

## NEXT GATE

`IMVERA_LIVEKIT_MEDIA_GATE=1` + `make livekit-media-gate` on Linux → nonzero PCM in `raw_inbound.wav`
