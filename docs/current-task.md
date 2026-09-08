# Current task — Self-hosted LiveKit telephony (ADR-012)

**Outcome:** Production telephony = **LiveKit SIP + LiveKit Server** (self-hosted, `livekit.rtc` only — NOT Agents framework).

## Done (hardening PR)

- [x] `livekit.yaml` — `udp_port: 7882` WebRTC mux (removed 10000–20000 from server config)
- [x] Firewall docs: 7882 = IMVERA participant; 10000–20000 = SIP RTP
- [x] `make livekit-up` prints public IP + port summary
- [x] `make livekit-health` — 9 separate component statuses
- [x] Opaque `call_id` (`lk-<uuid>`), redacted `room_ref` / `participant_ref` in traces
- [x] Session FSM + `TRACK_TIMEOUT` + `MEDIA_READY` before `CallActor.on_media_ready()`
- [x] `CALL_NOT_READY` if STT/TTS/LLM down before session start
- [x] Webhook idempotency: duplicate join, double close guard

## NOT VERIFIED

- Full synthetic SIP → GigaAM «хорошо» → UserTurn (needs Linux + livekit-up + voice stack)
- Barge-in full-duplex live test
- Real SIP trunk operator

## NEXT GATE

```bash
make livekit-up && make livekit-setup-sip
# voice gateway + STT/TTS/LLM up
IMVERA_LIVEKIT_GATE_REQUIRE_STACK=1 make livekit-sip-gate
```

Acceptance: synthetic SIP «хорошо» → nonzero inbound PCM → GigaAM → Vera outbound track → zero Vera in raw_inbound.wav
