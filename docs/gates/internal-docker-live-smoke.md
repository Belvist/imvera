# Phase A — internal docker live smoke (diagnostic)

Proves IMVERA path **inside** docker-compose network. Does **not** prove external Mac/LAN telephony.

## Path

```text
internal-blackbox-gate (pyVoIP, legacy_lab)
  → SIP freeswitch:5060 (docker network)
  → RTP internal
  → mod_audio_stream → host bridge (host.docker.internal:9210)
  → CallActor → STT → DialogueEngine → TTS
```

## Command

```bash
make internal-docker-live-smoke-1
```

Optional ladder (max 10 for runtime stability check):

```bash
IMVERA_INTERNAL_DOCKER_CALLS=10 make internal-docker-live-smoke-10
```

## Success label

```text
INTERNAL_DOCKER_LIVE_SMOKE = PASS
```

Not `TELEPHONY ACCEPTED`.

## Evidence

```text
.run/live_debug/<run_id>/call-001/
  caller_downlink.wav
  server_trace.jsonl
  trace_validation.json
  DEBUG_REPORT.md
```

## If FAIL

Debug IMVERA/FreeSWITCH/runtime — not Mac NAT.

## If PASS

Proceed to Phase B: `make pjsua2-transport-gate` then external `1 → 10 → 100`.
