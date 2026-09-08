# Current task — FreeSWITCH P0-A / P0-B gates (ADR-013)

**Outcome:** Split telephony proof from AI duplex bridge.

## P0-A — FreeSWITCH core (NOW)

No AI. Community `mod_audio_stream` **uplink only**. Outbound 880 Hz = **FS `tone_stream`**.

```text
440 Hz caller → FS → mod_audio_stream mono → bridge → raw_inbound.wav
FS tone_stream 880 Hz → caller
```

Acceptance: 1 → 10 → 100 calls.

```bash
make freeswitch-media-gate                    # unit
make freeswitch-up
python3 services/imvera_media_bridge/main.py  # uplink_only, no WS probe
IMVERA_FS_GATE_REQUIRE_STACK=1 make freeswitch-synthetic-sip
IMVERA_FS_GATE_REQUIRE_STACK=1 IMVERA_FS_SOAK_CALLS=100 make freeswitch-soak-gate
```

## P0-B — after P0-A 100/100

Build `mod_imvera_audio` (READ/WRITE WS). Wire CallActor. **Not** commercial mod_audio_stream bidirectional.

## NOT VERIFIED

- Live P0-A on Linux with mod_audio_stream built into FS image
- 100/100 soak

## NEXT GATE

P0-A `100/100` on Linux → start `mod_imvera_audio` design.
