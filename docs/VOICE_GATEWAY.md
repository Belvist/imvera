# Voice Gateway (Phase 6)

Foundation for streaming caller PCM from FreeSWITCH into MossVoice without
the record→HTTP turn loop.

## Architecture

```
FreeSWITCH (mod_audio_fork)
    → WebSocket ws://127.0.0.1:9720/stream
        → VoiceGatewayServer
            → GatewayVadBridge (Silero VAD, reuse voice_runtime/vad.py)
            → SmartTurnAnalyzer (MOSS_SMART_TURN=1, optional Pipecat)
    → on speech during playback: {"type":"cancel","generation_id":N}
    → on turn complete: {"type":"turn", ...}
```

Telephony `process_turn_stream` already tags every segment with
`generation_id` and honours `cancel_event`. The gateway cancel message
should call `on_generation_cancelled_for_call()` (conversation v2 bridge)
and bump `CallContext.generation_id` — same contract as ESL barge-in.

## FreeSWITCH integration (documented, not wired in dialplan yet)

Example dialplan snippet (requires `mod_audio_fork`):

```xml
<action application="set" data="api_on_answer=uuid_audio_fork ${uuid} start ws://127.0.0.1:9720/stream mono 16000"/>
```

PCM format: mono int16 little-endian @ 16 kHz (matches `voice_runtime/vad.py`).

Control JSON (text WebSocket frames):

| type | fields | meaning |
|------|--------|---------|
| `playback_start` | `generation_id` | Vera started playing |
| `playback_stop` | — | playback ended |
| `cancel` (outbound) | `generation_id`, `reason` | barge-in → abort TTS |

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `MOSS_VOICE_GATEWAY_HOST` | `127.0.0.1` | bind address |
| `MOSS_VOICE_GATEWAY_PORT` | `9720` | WebSocket port |
| `MOSS_VOICE_GATEWAY_PATH` | `/stream` | URL path |
| `MOSS_SMART_TURN` | `0` | enable Smart Turn placeholder |

## Run (dev)

```bash
python3 -c "
from voice_runtime.voice_gateway import VoiceGatewayServer
gw = VoiceGatewayServer(on_cancel=print, on_turn=print)
gw.start_background()
import time; time.sleep(3600)
"
```

Requires: `pip install websockets`

## Not verified in CI

- Live mod_audio_fork on FreeSWITCH
- Pipecat Smart Turn model install
- End-to-end cancel with Zoiper RTP
