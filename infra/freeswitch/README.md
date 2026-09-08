# FreeSWITCH production telephony (ADR-013)

## Two independent gates

### P0-A — prove FreeSWITCH telephony core (current)

No AI. No bridge WS outbound. Community `mod_audio_stream` = **uplink READ only**.

```text
caller 440 Hz
    ↓
FreeSWITCH answer
    ↓
mod_audio_stream mono → imvera-media-bridge → raw_inbound.wav

FreeSWITCH tone_stream 880 Hz → caller ear
```

Acceptance:

- INVITE → 200 OK
- 440 Hz in `raw_inbound.wav`
- 880 Hz **not** in `raw_inbound.wav`
- 880 Hz in synthetic caller downlink capture
- hangup cleanup
- soak: 1 → 10 → 100

### P0-B — duplex bridge (after P0-A 100/100)

Custom `mod_imvera_audio` (not commercial `mod_audio_stream` bidirectional):

```text
FS READ  → WS → IMVERA
IMVERA   → WS → FS WRITE
```

Then wire CallActor (VAD/GigaAM/LLM/TTS).

## Run P0-A (Linux)

```bash
# 1. Build FS image with mod_audio_stream (see MOD_AUDIO_STREAM.md)
export IMVERA_MEDIA_BRIDGE_WS=ws://host.docker.internal:9210/stream
make freeswitch-up

# 2. Uplink-only bridge (no 880 Hz probe)
python3 services/imvera_media_bridge/main.py

# 3. Unit gate
make freeswitch-media-gate

# 4. Live synthetic (requires pyVoIP + FS)
IMVERA_FS_GATE_REQUIRE_STACK=1 python3 scripts/freeswitch_synthetic_sip_media.py

# 5. Soak
IMVERA_FS_GATE_REQUIRE_STACK=1 IMVERA_FS_SOAK_CALLS=100 make freeswitch-soak-gate
```

## Dialplan

`conf/dialplan/public.xml`:

- `answer`
- `uuid_audio_stream` mono 16k (READ)
- `&tone_stream://%(25000,0,880)` (FS native downlink probe)

## License boundary

See [MOD_AUDIO_STREAM.md](./MOD_AUDIO_STREAM.md). P0-A uses community uplink only.
