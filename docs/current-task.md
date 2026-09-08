# Current task — FreeSWITCH cleanup + P0 transport gate (ADR-013)

**Outcome:** Single production telephony path. Legacy LiveKit/Telnyx/Asterisk removed from active runtime.

## Production path (only)

```text
SIP → FreeSWITCH (answers) → PCM WS bridge → imvera-media-bridge → (later) CallActor
```

## Cleanup done

- LiveKit → `archive/telephony/livekit/`
- Telnyx → `archive/telephony/telnyx/`
- Asterisk → `lab/asterisk/`
- Generic gate tools → `tools/telephony_gate/`
- `voice_gateway` — no LiveKit/Telnyx/Asterisk routes

## P0 gate (no GigaAM/STT/LLM/TTS)

```bash
make freeswitch-media-gate          # unit first
make freeswitch-up                  # requires mod_audio_stream in FS image
python3 services/imvera_media_bridge/main.py
# synthetic SIP 440 Hz → FS → bridge → raw_inbound.wav
```

Acceptance: 100/100 answer + 880 out + 440 in + directional + cleanup.

## mod_audio_stream

P0 validation OK. Production must choose licensed bidirectional OR `mod_imvera_audio` — see ADR-013 + `infra/freeswitch/MOD_AUDIO_STREAM.md`.

## NEXT GATE

Live Linux: 1 call → 10 → 100 synthetic duplex before AI on phone.
