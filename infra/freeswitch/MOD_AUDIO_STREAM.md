# mod_audio_stream — license boundary (ADR-013)

Repository: https://github.com/amigniter/mod_audio_stream  
FreeSWITCH image: `safarov/freeswitch:1.10.11` (pin before production build)

## Edition boundary (upstream README)

| Edition | Capability |
|---------|------------|
| Community | Primarily **uplink** streaming to WebSocket |
| Commercial v1.0.3+ | Bidirectional playback; free tier ≤10 concurrent channels |

## How we use it

| Gate | mod_audio_stream | Outbound audio |
|------|------------------|----------------|
| **P0-A** (now) | Community **READ/mono** only | FreeSWITCH `tone_stream` 880 Hz |
| **P0-B** (next) | **Not used** for duplex | Custom `mod_imvera_audio` |

P0-A proves FreeSWITCH answer + SIP/RTP + uplink PCM without AI and without commercial license.

P0-B must **not** silently depend on commercial bidirectional `mod_audio_stream`.

## Production decision (before CallActor on phone)

Choose explicitly:

- **A)** License bidirectional `mod_audio_stream` (with concurrency limits), or  
- **B)** Ship `mod_imvera_audio` on FreeSWITCH media-bug API (preferred)

No silent fallback between A and B.

## Build checklist (before live P0-A)

- [ ] Pin exact upstream commit/tag
- [ ] Document FreeSWITCH + module build steps in Dockerfile
- [ ] Verify `uuid_audio_stream` mono = caller-only on test call
- [ ] Verify `tone_stream` 880 Hz on caller downlink before sending 440 Hz uplink
