# Live SIP black-box E2E gate

Authoritative production acceptance for voice runtime — **real SIP/RTP**, no WebSocket injection, no ScenarioRunner.

## Architecture

```text
tools/blackbox_caller (pyVoIP)
  → SIP/RTP → host:5060 (same as Zoiper)
  → FreeSWITCH → mod_audio_stream → CallActor → … → RTP downlink
  → caller_downlink.wav → independent ASR → external oracle
```

Server trace (`.run/traces/fs-*.jsonl`) is **secondary** evidence only.

## Prerequisites

1. Stack up: `make freeswitch-zoiper-voice-up`
2. SIP account: `fs-gate-caller` / `gate` (or set `IMVERA_LIVE_SIP_USER/PASSWORD`)
3. **LAN IP** — not `127.0.0.1` for RTP: `make freeswitch-zoiper-info`
4. pyVoIP: `pip install -e '.[sip-lab]'`
5. Uplink WAV assets: `tests/assets/blackbox_voice/wav/`
   - **L3-A smoke:** `make blackbox-synthesize-vera` (Vera Silero TTS — NOT human)
   - **L3-B/L4:** human recordings — see `tests/assets/blackbox_voice/README.md`
6. Independent ASR: `whisper` CLI or `IMVERA_BLACKBOX_ASR_CMD`

L3-A Vera-self synthesis (smoke only):

```bash
make blackbox-synthesize-vera
```

Replace with human voice bank before G.722/PSTN acceptance.

Record human prompts manually:

```bash
python3 scripts/blackbox_record_prompts.py --list
python3 scripts/blackbox_record_prompts.py --record wellness_good_01
```

Replace macOS `say` recordings with real human speech before claiming telephony acceptance.

## Commands

```bash
# One call — stop on fail
make live-call-1

# Soak ladder
IMVERA_LIVE_CALLS=10 make live-call-soak
IMVERA_LIVE_CALLS=100 make live-call-soak

# PSTN (future)
IMVERA_LIVE_TRANSPORT=pstn IMVERA_LIVE_CALLS=100 make live-call-soak
```

Environment:

| Variable | Default | Purpose |
|----------|---------|---------|
| `IMVERA_LIVE_SIP_HOST` | LAN IP from profile | External SIP target |
| `IMVERA_LIVE_EXTENSION` | `7000` | Vera extension |
| `IMVERA_LIVE_CALLS` | `10` | Soak count |
| `IMVERA_LIVE_STOP_ON_FAIL` | `1` | Stop ladder on first failure |
| `IMVERA_BLACKBOX_ASR_CMD` | (empty) | External ASR shell command with `{wav}` |
| `IMVERA_LIVE_CLIENT_IP` | auto | Client RTP source IP |

## Evidence

```text
.run/live_e2e/<run_id>/
  call-001/
    caller_downlink.wav
    external_bot_transcript.txt
    external_assertions.json
    server_trace.jsonl
    result.json
  summary.json
```

## Anti-cheating

`summary.json` includes:
- `production_git_sha`
- `mocked_components: 0`
- `external_sip: true`
- `independent_bot_transcription: true`

Import guard: if `tools/blackbox_caller` loads `packages.dialogue_engine` or `CallActor` → **BLACKBOX_GATE=FAIL**.

## Scenario catalog

500 deterministic scenarios (5 wellness × 20 families × 5 variants):

```bash
make blackbox-write-catalog
# → tools/blackbox_caller/scenarios/catalog.json
```

Live soak uses first N scenarios in deterministic order for the 1→10→100 ladder.

## Gate levels

| Level | Command | Proves |
|-------|---------|--------|
| L2 Dialogue | `make dialogue-corpus-gate` | Engine FSM 500/500 |
| L3 Live SIP | `make live-call-soak` | Real voice + telephony |
| L4 PSTN | `IMVERA_LIVE_TRANSPORT=pstn` | Production operator path |

Only **100/100 consecutive live calls** on one unchanged build grants `TELEPHONY = ACCEPTED`.

## NOT VERIFIED by default CI

- Live SIP calls (no human WAV in repo)
- PJSUA2 (pyVoIP used; PJSUA2 documented as upgrade path)
- 100/100 soak
